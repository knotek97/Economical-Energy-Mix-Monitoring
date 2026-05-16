"""
fetcher.py — ENTSO-E data retrieval via entsoe-py

Changes from original:
  - API key: reads from Streamlit secrets first, falls back to .env (server-safe)
  - Retry logic: exponential backoff on 503/429 errors (up to 3 attempts)
  - Caching: SQLite via cache_db.db_cached (replaces @st.cache_data)
"""

import os
import time
import logging
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError
from requests.exceptions import HTTPError
from dotenv import load_dotenv

from data.cache_db import db_cached, TTL_PRICES, TTL_GENERATION, TTL_CAPACITY

load_dotenv()
logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    try:
        import streamlit as st
        key = st.secrets.get("ENTSOE_API_KEY")
        if key:
            return key
    except Exception:
        pass
    key = os.getenv("ENTSOE_API_KEY")
    if key:
        return key
    raise EnvironmentError(
        "ENTSOE_API_KEY not found.\n"
        "Add it to .streamlit/secrets.toml:  ENTSOE_API_KEY = 'your-key'\n"
        "Or to .env:                          ENTSOE_API_KEY=your-key"
    )


def get_client() -> EntsoePandasClient:
    return EntsoePandasClient(api_key=_get_api_key())


def _with_retry(fn, max_attempts: int = 3, base_delay: float = 2.0):
    """Exponential backoff on 503/429. Re-raises immediately on other errors."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except NoMatchingDataError:
            raise
        except HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (503, 429):
                last_exc = e
                delay = base_delay * (2 ** attempt)
                logger.warning("ENTSO-E %d — retry %d/%d in %.0fs",
                               status, attempt + 1, max_attempts, delay)
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            last_exc = e
            delay = base_delay * (2 ** attempt)
            logger.warning("ENTSO-E error attempt %d/%d: %s — retry in %.0fs",
                           attempt + 1, max_attempts, e, delay)
            time.sleep(delay)
    raise last_exc


GENERATION_DOMAIN_OVERRIDES: dict[str, str] = {
    "PL":      "10YPL-AREA-----S",
    "GR":      "10YGR-HTSO-----Y",
    "NO":      "10YNO-0--------C",
    "SE_3":    "10Y1001A1001A46L",
    "IT_NORD": "10Y1001A1001A73I",   # renamed from IT_NORTH
    "DK":      "10Y1001A1001A65H",   # TSO area — fine for generation
}

# Day-ahead prices use bidding zone codes, not TSO area codes.
# Some countries publish prices per sub-zone only — e.g. Denmark has
# no combined day-ahead price; only DK_1 (West) and DK_2 (East) exist.
PRICE_DOMAIN_OVERRIDES: dict[str, str] = {
    "DK":      "DK_1",    # West Denmark (largest zone, most wind capacity)
    "IT_NORD": "IT_NORD", # Correct entsoe-py name (was mistakenly IT_NORTH)
    "NO":      "NO_1",    # Norway — NO_1 is the reference zone (Oslo)
}


@db_cached(ttl=TTL_PRICES)
def fetch_day_ahead_prices(country_code: str, start: datetime, end: datetime) -> pd.Series:
    """Hourly day-ahead prices (EUR/MWh). SQLite-cached 1h. Retries on 503/429.

    Uses PRICE_DOMAIN_OVERRIDES for countries where:
      - The combined area code has no day-ahead price (e.g. DK → DK_1)
      - The code name differs from entsoe-py's Area enum (e.g. IT_NORD)
    """
    client     = get_client()
    ts_start   = pd.Timestamp(start, tz="Europe/Brussels")
    ts_end     = pd.Timestamp(end,   tz="Europe/Brussels")
    query_code = PRICE_DOMAIN_OVERRIDES.get(country_code, country_code)
    return _with_retry(
        lambda: client.query_day_ahead_prices(query_code, start=ts_start, end=ts_end)
    )


@db_cached(ttl=TTL_GENERATION)
def fetch_generation(country_code: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Generation per production type (MW). SQLite-cached 1h. Retries on 503/429."""
    client     = get_client()
    ts_start   = pd.Timestamp(start, tz="Europe/Brussels")
    ts_end     = pd.Timestamp(end,   tz="Europe/Brussels")
    query_code = GENERATION_DOMAIN_OVERRIDES.get(country_code, country_code)
    gen = _with_retry(
        lambda: client.query_generation(query_code, start=ts_start, end=ts_end, psr_type=None)
    )
    if isinstance(gen.columns, pd.MultiIndex):
        gen = gen.xs("Actual Aggregated", axis=1, level=1)
    return gen


@db_cached(ttl=TTL_CAPACITY)
def fetch_installed_capacity(country_code: str, n_years: int = 5) -> pd.DataFrame:
    """Installed capacity (MW) per source per year. Parallel fetch. SQLite-cached 24h."""
    client       = get_client()
    current_year = pd.Timestamp.now().year
    query_code   = GENERATION_DOMAIN_OVERRIDES.get(country_code, country_code)

    def _fetch_year(year: int):
        ts_s = pd.Timestamp(f"{year}-01-01", tz="Europe/Brussels")
        ts_e = pd.Timestamp(f"{year}-12-31", tz="Europe/Brussels")
        try:
            cap = _with_retry(
                lambda: client.query_installed_generation_capacity(
                    query_code, start=ts_s, end=ts_e, psr_type=None
                )
            )
            if isinstance(cap.columns, pd.MultiIndex):
                cap = cap.xs("Actual Aggregated", axis=1, level=1, drop_level=True)
            if len(cap) > 0:
                return year, cap.iloc[-1].rename(year)
        except Exception as e:
            logger.debug("No capacity for %s/%d: %s", country_code, year, e)
        return None

    frames = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_year, y): y
                   for y in range(current_year - n_years, current_year + 1)}
        for f in as_completed(futures):
            r = f.result()
            if r:
                frames.append(r[1])

    if not frames:
        return pd.DataFrame()
    frames.sort(key=lambda s: s.name)
    df = pd.DataFrame(frames)
    df.index.name = "Year"
    df = df.dropna(axis=1, how="all")
    df = df.loc[:, (df != 0).any(axis=0)]
    return df.fillna(0)


def mock_prices(start, end):
    import numpy as np
    idx = pd.date_range(start, end, freq="h", tz="Europe/Brussels")
    np.random.seed(42)
    return pd.Series(
        50 + 30 * np.sin(np.linspace(0, 4 * np.pi, len(idx))) + np.random.normal(0, 5, len(idx)),
        index=idx
    )


def mock_generation(start, end):
    import numpy as np
    idx = pd.date_range(start, end, freq="h", tz="Europe/Brussels")
    np.random.seed(42)
    return pd.DataFrame({
        "Solar":         np.abs(np.random.normal(2000, 500,  len(idx))),
        "Wind Onshore":  np.abs(np.random.normal(4000, 1000, len(idx))),
        "Nuclear":       np.abs(np.random.normal(3000, 200,  len(idx))),
        "Fossil Gas":    np.abs(np.random.normal(1500, 400,  len(idx))),
        "Hydro Run-of-river and poundage": np.abs(np.random.normal(800, 100, len(idx))),
    }, index=idx)
