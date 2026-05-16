"""
eurostat.py — Eurostat data retrieval (no API key needed)

Uses the Eurostat REST API:
  https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/

Datasets:
  prc_hicp_manr   → HICP monthly inflation (annual rate of change)
                    CP00 = All items (general CPI)
                    CP04 = Housing, water, electricity, gas and other fuels

  nrg_pc_204      → Household electricity prices (bi-annual, €/kWh)
                    Consumption band DC: 2500–4999 kWh/year (typical household)
                    unit=KWH, currency=EUR, tax=X_TAX (excl. taxes)

  nrg_ind_id      → Energy import dependency (annual, %)
                    siec=TOTAL (all energy products combined)
                    A positive value = net importer; negative = net exporter
"""

import requests
import pandas as pd
from data.cache_db import db_cached, TTL_INFLATION, TTL_HOUSEHOLD, TTL_IMPORT_DEP

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

# ── ENTSO-E bidding zone → Eurostat 2-letter country code ────────────────────
ENTSOE_TO_EUROSTAT = {
    "AL":        "AL",
    "AT":        "AT",
    "BA":        "BA",
    "BE":        "BE",
    "BG":        "BG",
    "CH":        "CH",
    "CY":        "CY",
    "CZ":        "CZ",
    "DE_LU":     "DE",   # Germany/Luxembourg bidding zone → Germany stats
    "DK":        "DK",
    "EE":        "EE",
    "ES":        "ES",
    "FI":        "FI",
    "FR":        "FR",
    "GB":        "UK",   # Eurostat uses 'UK' not 'GB'
    "GB-NIR":    "UK",
    "GR":        "EL",   # Eurostat uses 'EL' for Greece
    "HR":        "HR",
    "HU":        "HU",
    "IE":        "IE",
    "IT":        "IT",
    "IT_NORD":   "IT",   # correct entsoe-py code (was IT_NORTH)
    "IT_NORTH":  "IT",   # kept for backwards compatibility
    "IT_CNOR":   "IT",   # entsoe-py Central North Italy
    "IT_CNORTH": "IT",   # legacy alias
    "IT_CSUD":   "IT",   # entsoe-py Central South Italy
    "IT_CSOUTH": "IT",   # legacy alias
    "IT_SUD":    "IT",   # entsoe-py South Italy
    "IT_SOUTH":  "IT",   # legacy alias
    "IT_SICI":   "IT",
    "IT_SARD":   "IT",
    "LT":        "LT",
    "LU":        "LU",
    "LV":        "LV",
    "ME":        "ME",
    "MK":        "MK",
    "MT":        "MT",
    "NL":        "NL",
    "NO":        "NO",
    "PL":        "PL",
    "PT":        "PT",
    "RO":        "RO",
    "RS":        "RS",
    "SE_1":      "SE",
    "SE_2":      "SE",
    "SE_3":      "SE",
    "SE_4":      "SE",
    "SI":        "SI",
    "SK":        "SK",
    "TR":        "TR",
    "UA":        "UA",
}


def entsoe_to_eurostat(entsoe_code: str) -> str | None:
    """Convert an ENTSO-E bidding zone code to a Eurostat country code."""
    return ENTSOE_TO_EUROSTAT.get(entsoe_code)


# ── Shared JSON-stat parser ───────────────────────────────────────────────────
def _parse_jsonstat(data: dict, time_dim: str = "time") -> dict:
    """
    Parse the Eurostat JSON-stat response format into a plain dict of
    {time_label: value}. Skips missing values (None).

    Parameters
    ----------
    data     : the parsed JSON response
    time_dim : the dimension key that holds the time labels (usually "time")
    """
    values      = data["value"]
    time_labels = list(data["dimension"][time_dim]["category"]["label"].values())

    result = {}
    for str_idx, label in enumerate(time_labels):
        val = values.get(str(str_idx))
        if val is not None:
            result[label] = val
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 1. HICP Inflation  (prc_hicp_manr)
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_hicp(eurostat_code: str, coicop: str, n_years: int = 5) -> pd.Series:
    """
    Fetch HICP monthly inflation (annual rate of change) from Eurostat.

    Parameters
    ----------
    eurostat_code : e.g. 'AT', 'DE', 'EL'
    coicop        : 'CP00' (all items) or 'CP04' (energy/housing)
    n_years       : years of history to fetch

    Returns
    -------
    pd.Series indexed by monthly Period, values = % annual rate of change
    """
    url    = f"{EUROSTAT_BASE}/prc_hicp_manr"
    params = {
        "format":          "JSON",
        "lang":            "EN",
        "unit":            "RCH_A",
        "coicop":          coicop,
        "geo":             eurostat_code,
        "sinceTimePeriod": f"{pd.Timestamp.now().year - n_years}-01",
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    series_data = _parse_jsonstat(resp.json())

    if not series_data:
        raise ValueError(f"No HICP data for {eurostat_code} / {coicop}")

    s = pd.Series(series_data, name=coicop)
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.sort_index()


@db_cached(ttl=TTL_INFLATION)
def fetch_inflation(entsoe_code: str, n_years: int = 5) -> dict:
    """
    Fetch general CPI and energy CPI for a given ENTSO-E country code.

    Returns
    -------
    dict with keys:
      'eurostat_code' : str
      'cpi'           : pd.Series  (monthly % YoY)
      'energy'        : pd.Series  (monthly % YoY)
      'latest_cpi'    : float
      'latest_energy' : float
    """
    eurostat_code = entsoe_to_eurostat(entsoe_code)
    if not eurostat_code:
        raise ValueError(f"No Eurostat mapping for ENTSO-E code: {entsoe_code}")

    cpi    = _fetch_hicp(eurostat_code, "CP00", n_years)
    energy = _fetch_hicp(eurostat_code, "CP04", n_years)

    return {
        "eurostat_code": eurostat_code,
        "cpi":           cpi,
        "energy":        energy,
        "latest_cpi":    round(float(cpi.iloc[-1]), 2),
        "latest_energy": round(float(energy.iloc[-1]), 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. Household Electricity Prices  (nrg_pc_204)
# ══════════════════════════════════════════════════════════════════════════════
@db_cached(ttl=TTL_HOUSEHOLD)
def fetch_household_electricity_price(
    entsoe_code: str,
    n_years: int = 10,
    include_taxes: bool = False,
) -> pd.Series:
    """
    Fetch bi-annual household electricity prices from Eurostat (nrg_pc_204).

    This is the consumer-facing price — not the wholesale day-ahead market price.
    It is the most relevant indicator for the inflation impact on households.

    Parameters
    ----------
    entsoe_code   : ENTSO-E bidding zone code, e.g. 'DE_LU', 'AT', 'FR'
    n_years       : years of history (data available from 2007)
    include_taxes : if True, returns price including all taxes (I_TAX)
                    if False (default), returns price excluding taxes (X_TAX)
                    Excluding taxes is more comparable across countries because
                    tax levels vary enormously between EU members.

    Returns
    -------
    pd.Series
        Index : string labels like '2020-S1', '2020-S2'
        Values: price in €/kWh (average across all consumption bands)

    Notes
    -----
    - Uses nrg_cons=TOT_KWH (all consumption bands combined) for maximum
      country coverage. Individual bands like KWH2500-4999 are not reported
      by all countries (e.g. Germany and France only report TOT_KWH).
    - Data is bi-annual: S1 = Jan–Jun average, S2 = Jul–Dec average
    - Switzerland (CH) and some non-EU countries may have limited coverage
    """
    eurostat_code = entsoe_to_eurostat(entsoe_code)
    if not eurostat_code:
        raise ValueError(f"No Eurostat mapping for ENTSO-E code: {entsoe_code}")

    tax_code      = "I_TAX" if include_taxes else "X_TAX"
    # nrg_pc_204 is bi-annual (2 semesters/year).
    # sinceTimePeriod only accepts plain years — semester strings like "2021S1"
    # are rejected with a 400. We use lastTimePeriod (number of observations)
    # instead: n_years × 2 semesters per year.
    last_n = n_years * 2

    # Fetch without filtering nrg_cons — let Eurostat return all bands.
    # URLs are built as f-strings (not requests params) because hyphens in
    # band codes must NOT be percent-encoded (%2D) — Eurostat rejects them.
    # Note: product=6000 is NOT a dimension in nrg_pc_204 (only in nrg_pc_204_v).
    url = (
        f"{EUROSTAT_BASE}/nrg_pc_204"
        f"?format=JSON&lang=EN"
        f"&unit=KWH"
        f"&currency=EUR"
        f"&tax={tax_code}"
        f"&geo={eurostat_code}"
        f"&lastTimePeriod={last_n}"
    )

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # ── Parse multi-dimensional JSON-stat ────────────────────────────────────
    # The value array is flattened across ALL dimensions in order.
    # We need to reconstruct (nrg_cons, time) → value.
    dims       = data["id"]                  # ordered list of dimension ids
    sizes      = data["size"]                # size of each dimension
    values_raw = data["value"]               # {flat_index_str: value}

    # Extract category labels for nrg_cons and time
    nrg_cons_labels = list(
        data["dimension"]["nrg_cons"]["category"]["label"].keys()
    )
    time_labels = list(
        data["dimension"]["time"]["category"]["label"].values()
    )

    nrg_cons_idx = dims.index("nrg_cons")
    time_idx     = dims.index("time")

    # Compute strides (how many flat positions one step in each dim covers)
    strides = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    # Build {band: {time_label: value}}
    band_data: dict[str, dict] = {}
    for b_pos, band in enumerate(nrg_cons_labels):
        band_data[band] = {}
        for t_pos, tlabel in enumerate(time_labels):
            # Compute flat index assuming all other dims have index 0
            flat = b_pos * strides[nrg_cons_idx] + t_pos * strides[time_idx]
            val  = values_raw.get(str(flat))
            if val is not None:
                band_data[band][tlabel] = val

    # Pick the band with the most data points — prefer specific bands over TOT_KWH
    BAND_PRIORITY = [
        "KWH2500-4999", "KWH1000-2499", "KWH_LT1000",
        "KWH5000-14999", "KWH_GE15000", "TOT_KWH",
    ]
    best_band   = None
    best_series = {}
    for band in BAND_PRIORITY:
        if band_data.get(band):
            best_band   = band
            best_series = band_data[band]
            break

    # If none of the preferred bands have data, take whatever has the most points
    if not best_series:
        best_band, best_series = max(
            band_data.items(), key=lambda x: len(x[1]), default=(None, {})
        )

    if not best_series:
        raise ValueError(
            f"No household electricity price data found for {eurostat_code}. "
            "This country may not report to Eurostat nrg_pc_204."
        )

    # Convert Eurostat's '2020S1' / '2020S2' → '2020-S1' / '2020-S2' for readability.
    # Sort by (year, semester) as integers — never alphabetically.
    # Labels without an 'S' (unexpected format) are placed at the end.
    sort_items = []
    for k, v in best_series.items():
        if "S" in k:
            try:
                year_str, sem_str = k.split("S", 1)
                sort_items.append((int(year_str), int(sem_str), f"{year_str}-S{sem_str}", v))
            except ValueError:
                sort_items.append((9999, 9999, k, v))
        else:
            sort_items.append((9999, 9999, k, v))

    sort_items.sort(key=lambda x: (x[0], x[1]))
    s = pd.Series(
        {label: val for _, _, label, val in sort_items},
        name=f"hp_{best_band}",
        dtype=float,
    )
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 3. Energy Import Dependency  (nrg_ind_id)
# ══════════════════════════════════════════════════════════════════════════════
@db_cached(ttl=TTL_IMPORT_DEP)
def fetch_energy_import_dependency(
    entsoe_code: str,
    n_years: int = 10,
) -> pd.Series:
    """
    Fetch annual energy import dependency from Eurostat (nrg_ind_id).

    This is the key causal link in our thesis:
      High renewable capacity → lower import dependency → less exposure to
      global fossil fuel price shocks → lower and more stable energy CPI.

    Parameters
    ----------
    entsoe_code : ENTSO-E bidding zone code, e.g. 'DE_LU', 'AT', 'FR'
    n_years     : years of history (data available from 1990)

    Returns
    -------
    pd.Series
        Index : year (int)
        Values: import dependency (%) — total energy, all products combined
                Positive = net importer (depends on foreign energy)
                Negative = net exporter (produces more than it consumes)

    Notes
    -----
    - Uses siec=TOTAL: all energy products combined (gas, oil, coal, electricity)
    - A country with high renewables will tend to show a declining trend here
      over time as it replaces imported fossil fuels with domestic renewables
    - Values can exceed 100% (some re-export countries) or go negative
      (net exporters like Norway)
    """
    eurostat_code = entsoe_to_eurostat(entsoe_code)
    if not eurostat_code:
        raise ValueError(f"No Eurostat mapping for ENTSO-E code: {entsoe_code}")

    since_year = pd.Timestamp.now().year - n_years

    url    = f"{EUROSTAT_BASE}/nrg_ind_id"
    params = {
        "format":          "JSON",
        "lang":            "EN",
        "siec":            "TOTAL",   # all energy products
        "unit":            "PC",      # percentage
        "geo":             eurostat_code,
        "sinceTimePeriod": str(since_year),
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    series_data = _parse_jsonstat(resp.json())

    if not series_data:
        raise ValueError(
            f"No energy import dependency data for {eurostat_code}."
        )

    s = pd.Series(series_data, name="energy_import_dependency_pct", dtype=float)
    s.index = s.index.astype(int)
    return s.sort_index()
