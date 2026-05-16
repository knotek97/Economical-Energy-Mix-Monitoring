"""
cache_db.py — SQLite-based persistent cache for the Energy & Economics Dashboard

Replaces the pickle file cache (cache.py) with a single SQLite database.

Advantages over pickle files for a web server:
  - Safe for concurrent reads from multiple browser sessions
  - Atomic writes — no corrupt files if the server crashes mid-write
  - Queryable — inspect cache state without loading data
  - Single file to back up, move, or clear
  - Works in read-only app directories (configurable path via env var)

Schema:
  cache_entries(key TEXT PRIMARY KEY, value BLOB, updated_at REAL, ttl INTEGER)

Cache path priority:
  1. ENERGY_CACHE_DIR environment variable
  2. /tmp/energy_dashboard/  (always writable on any server)
  3. .cache/ next to this file (local dev fallback)
"""

import os
import time
import pickle
import sqlite3
import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── TTLs (seconds) ────────────────────────────────────────────────────────────
TTL_PRICES        = 3_600      #  1 hour  — day-ahead prices
TTL_GENERATION    = 3_600      #  1 hour  — generation mix
TTL_CAPACITY      = 86_400     # 24 hours — installed capacity
TTL_INFLATION     = 43_200     # 12 hours — Eurostat HICP
TTL_HOUSEHOLD     = 259_200    # 72 hours — household electricity prices
TTL_IMPORT_DEP    = 259_200    # 72 hours — energy import dependency

# ── DB path ───────────────────────────────────────────────────────────────────
def _db_path() -> Path:
    """
    Resolve the cache database path.
    Priority: ENERGY_CACHE_DIR env var → /tmp → local .cache/
    """
    env = os.environ.get("ENERGY_CACHE_DIR")
    if env:
        p = Path(env)
    else:
        # /tmp is always writable on Linux servers and Streamlit Cloud
        p = Path("/tmp/energy_dashboard")

    try:
        p.mkdir(parents=True, exist_ok=True)
        # Quick write test
        test = p / ".write_test"
        test.touch()
        test.unlink()
        return p / "cache.db"
    except OSError:
        # Fall back to local .cache/ for dev environments
        fallback = Path(__file__).parent / ".cache"
        fallback.mkdir(exist_ok=True)
        return fallback / "cache.db"


DB_PATH = _db_path()

# Thread-local SQLite connections — one per thread, avoids "used from multiple threads" errors
_local = threading.local()


def _conn() -> sqlite3.Connection:
    """Get (or create) a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")   # allows concurrent reads + one write
        _local.conn.execute("PRAGMA synchronous=NORMAL") # faster writes, still safe
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                key        TEXT PRIMARY KEY,
                value      BLOB NOT NULL,
                updated_at REAL NOT NULL,
                ttl        INTEGER NOT NULL
            )
        """)
        _local.conn.commit()
    return _local.conn


# ── Public API ────────────────────────────────────────────────────────────────
def cache_key(*args: Any) -> str:
    """Deterministic cache key from arbitrary arguments."""
    raw = str(args).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def db_get(key: str) -> tuple[Any, float] | None:
    """
    Fetch a cached value.
    Returns (value, updated_at) if the entry exists and is not expired.
    Returns None on miss, expiry, or read error.
    """
    try:
        row = _conn().execute(
            "SELECT value, updated_at, ttl FROM cache_entries WHERE key = ?",
            (key,)
        ).fetchone()
        if row is None:
            return None
        value_blob, updated_at, ttl = row
        if time.time() - updated_at > ttl:
            logger.debug("Cache expired: %s (age %.0fs > ttl %ds)",
                         key[:8], time.time() - updated_at, ttl)
            return None
        return pickle.loads(value_blob), updated_at
    except Exception as e:
        logger.warning("Cache read error for %s: %s", key[:8], e)
        return None


def db_set(key: str, value: Any, ttl: int) -> None:
    """Write a value to the cache. Silently ignores write errors."""
    try:
        blob = pickle.dumps(value)
        _conn().execute(
            """INSERT OR REPLACE INTO cache_entries (key, value, updated_at, ttl)
               VALUES (?, ?, ?, ?)""",
            (key, blob, time.time(), ttl)
        )
        _conn().commit()
    except Exception as e:
        logger.warning("Cache write error for %s: %s", key[:8], e)


def db_cached(ttl: int) -> Callable:
    """
    Decorator — wraps a function with SQLite caching.
    Cache key is derived from function name + all arguments.

    Usage:
        @db_cached(ttl=TTL_INFLATION)
        def fetch_inflation(entsoe_code, n_years=5):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            key = cache_key(fn.__name__, args, sorted(kwargs.items()))
            result = db_get(key)
            if result is not None:
                logger.debug("Cache hit: %s%s", fn.__name__, args)
                return result[0]
            logger.debug("Cache miss: %s%s — fetching live", fn.__name__, args)
            data = fn(*args, **kwargs)
            db_set(key, data, ttl)
            return data
        wrapper.__name__ = fn.__name__
        wrapper.__doc__  = fn.__doc__
        return wrapper
    return decorator


def db_get_updated_at(fn_name: str, *args, **kwargs) -> float | None:
    """
    Return the unix timestamp when a specific cached result was last fetched.
    Used by the UI to show 'last updated' timestamps on charts.
    """
    key = cache_key(fn_name, args, sorted(kwargs.items()))
    try:
        row = _conn().execute(
            "SELECT updated_at FROM cache_entries WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def cache_info() -> list[dict]:
    """Return metadata about all cached entries for the sidebar panel."""
    try:
        rows = _conn().execute(
            "SELECT key, updated_at, ttl, length(value) FROM cache_entries "
            "ORDER BY updated_at DESC"
        ).fetchall()
        now = time.time()
        return [
            {
                "key":      r[0][:8] + "…",
                "age_min":  round((now - r[1]) / 60, 1),
                "ttl_h":    round(r[2] / 3600, 1),
                "size_kb":  round(r[3] / 1024, 1),
                "fresh":    (now - r[1]) < r[2],
            }
            for r in rows
        ]
    except Exception:
        return []


def clear_cache() -> int:
    """Delete all cache entries. Returns number deleted."""
    try:
        cur = _conn().execute("DELETE FROM cache_entries")
        _conn().commit()
        return cur.rowcount
    except Exception:
        return 0


def cache_stats() -> dict:
    """Summary stats for the sidebar."""
    try:
        row = _conn().execute(
            "SELECT COUNT(*), SUM(length(value)), "
            "SUM(CASE WHEN (? - updated_at) < ttl THEN 1 ELSE 0 END) "
            "FROM cache_entries",
            (time.time(),)
        ).fetchone()
        return {
            "total":   row[0] or 0,
            "fresh":   row[2] or 0,
            "size_kb": round((row[1] or 0) / 1024, 1),
        }
    except Exception:
        return {"total": 0, "fresh": 0, "size_kb": 0}
