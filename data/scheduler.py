"""
scheduler.py — Background pre-fetch scheduler for the Energy & Economics Dashboard

Runs as a daemon thread inside the Streamlit process.
Pre-fetches data for the most commonly used country pairs on a schedule,
so users never wait for a cold fetch.

Schedule:
  - On startup:    pre-fetch top country pairs (non-blocking, runs in background)
  - Every night:   refresh all stale Eurostat data at 02:00 CET
  - Every 2 hours: refresh ENTSO-E prices + generation for top countries

Why a background thread and not a separate cron job?
  For a single-server Streamlit deployment this is the simplest approach —
  no external scheduler (cron, Celery, APScheduler service) needed.
  The thread is a daemon so it dies cleanly when the app exits.
  For a multi-instance deployment you would move this to a separate worker.
"""

import time
import logging
import threading
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

# ── Top country pairs to pre-fetch ────────────────────────────────────────────
# These are the most academically interesting comparisons for the thesis.
# Prices + generation are fetched for a rolling 90-day window.
# Eurostat data is fetched for the default 5-year window.
TOP_COUNTRIES = [
    "DE_LU",    # Germany/Luxembourg
    "FR",       # France       (nuclear-heavy, interesting contrast)
    "ES",       # Spain        (high renewables growth)
    "PL",       # Poland       (coal-heavy, good contrast with Germany)
    "AT",       # Austria      (high renewables)
    "BE",       # Belgium      (nuclear + gas mix)
    "NL",       # Netherlands
    "DK",       # Denmark      (wind leader — prices fetched via DK_1 zone)
    "CZ",       # Czech Republic
    "IT_NORD",  # Italy North  (correct entsoe-py code — was mistakenly IT_NORTH)
]

# Rolling window for ENTSO-E prices/generation
ROLLING_DAYS = 90

_started    = False
_start_lock = threading.Lock()


def _fetch_eurostat_for(country_code: str, n_years: int = 5) -> None:
    """Pre-fetch all three Eurostat datasets for a country. Errors are logged, not raised."""
    # Import here to avoid circular imports at module load time
    from data.eurostat import fetch_inflation, fetch_household_electricity_price, fetch_energy_import_dependency

    for fn, label in [
        (lambda: fetch_inflation(country_code, n_years=n_years),               "inflation"),
        (lambda: fetch_household_electricity_price(country_code, n_years=n_years), "household prices"),
        (lambda: fetch_energy_import_dependency(country_code, n_years=n_years),    "import dependency"),
    ]:
        try:
            fn()
            logger.info("Scheduler: pre-fetched %s for %s", label, country_code)
        except Exception as e:
            logger.warning("Scheduler: %s failed for %s: %s", label, country_code, e)


def _fetch_entsoe_for(country_code: str) -> None:
    """Pre-fetch prices + generation for a rolling 90-day window."""
    from data.fetcher import fetch_day_ahead_prices, fetch_generation

    end   = pd.Timestamp.now().normalize()
    start = end - pd.Timedelta(days=ROLLING_DAYS)

    for fn, label in [
        (lambda: fetch_day_ahead_prices(country_code, start, end), "prices"),
        (lambda: fetch_generation(country_code, start, end),       "generation"),
    ]:
        try:
            fn()
            logger.info("Scheduler: pre-fetched %s for %s", label, country_code)
        except Exception as e:
            logger.warning("Scheduler: %s failed for %s: %s", label, country_code, e)


def _startup_prefetch() -> None:
    """
    Pre-fetch Eurostat data for all top countries on startup.
    Runs in a background thread so the app is responsive immediately.
    Staggers requests to avoid hammering the APIs.
    """
    logger.info("Scheduler: startup pre-fetch beginning for %d countries", len(TOP_COUNTRIES))
    for country in TOP_COUNTRIES:
        _fetch_eurostat_for(country)
        time.sleep(2)   # 2-second stagger between countries
    logger.info("Scheduler: startup pre-fetch complete")


def _nightly_refresh() -> None:
    """
    Refresh all Eurostat data for top countries.
    Scheduled to run at 02:00 CET daily.
    """
    logger.info("Scheduler: nightly refresh starting")
    for country in TOP_COUNTRIES:
        _fetch_eurostat_for(country)
        time.sleep(3)
    logger.info("Scheduler: nightly refresh complete")


def _hourly_refresh() -> None:
    """
    Refresh ENTSO-E prices and generation for top countries.
    Runs every 2 hours.
    """
    logger.info("Scheduler: hourly ENTSO-E refresh starting")
    for country in TOP_COUNTRIES:
        _fetch_entsoe_for(country)
        time.sleep(1)
    logger.info("Scheduler: hourly ENTSO-E refresh complete")


def _seconds_until(hour: int, minute: int = 0) -> float:
    """
    Return seconds until the next occurrence of HH:MM (local time).
    Used to schedule the nightly run.
    """
    now  = datetime.now()
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


def _scheduler_loop() -> None:
    """
    Main scheduler loop. Runs forever as a daemon thread.

    Timeline:
      t=0s        startup pre-fetch (Eurostat, background)
      t=0s+       every 2 hours: ENTSO-E refresh
      02:00 CET   nightly: full Eurostat refresh for all countries
    """
    # Startup pre-fetch runs immediately in a sub-thread so it doesn't
    # block the scheduler loop itself
    threading.Thread(target=_startup_prefetch, daemon=True, name="startup-prefetch").start()

    last_hourly  = 0.0
    HOURLY_INTERVAL = 2 * 3600   # 2 hours in seconds

    while True:
        now = time.time()

        # Nightly refresh at 02:00
        sleep_to_night = _seconds_until(2, 0)
        if sleep_to_night < 60:
            # We're within a minute of 02:00 — run nightly refresh
            _nightly_refresh()
            time.sleep(120)   # sleep 2 min to avoid double-triggering
            continue

        # Hourly ENTSO-E refresh
        if now - last_hourly >= HOURLY_INTERVAL:
            _hourly_refresh()
            last_hourly = now

        # Sleep 5 minutes between checks
        time.sleep(300)


def start_scheduler() -> None:
    """
    Start the background scheduler thread (idempotent — safe to call multiple times).

    Streamlit re-runs the entire script on every interaction, so we use a module-level
    flag + lock to ensure only one scheduler thread ever runs per process.
    """
    global _started
    with _start_lock:
        if _started:
            return
        _started = True

    thread = threading.Thread(
        target=_scheduler_loop,
        daemon=True,          # dies when the Streamlit process exits
        name="energy-scheduler",
    )
    thread.start()
    logger.info("Scheduler: background thread started (pid=%d)", __import__("os").getpid())
