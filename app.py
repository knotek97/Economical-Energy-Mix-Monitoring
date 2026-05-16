"""
app.py — Energy & Economics Dashboard (Streamlit)
Run with:  streamlit run app.py

Thesis: Countries that invested in renewables reduced fossil fuel dependency,
        which led to more stable energy prices and lower inflation.

Tab structure:
  1. 🌍 Structural View   — Long-term (5–10 years): installed capacity, renewable share trend
  2. 📈 Market Dynamics   — Medium-term (1–2 years): monthly prices, generation, CPI
  3. ⚡ Operational View  — Short-term (days/weeks): hourly prices, daily generation mix
  4. 🔀 Country Comparison — All horizons side by side
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

from data.fetcher import (
    fetch_day_ahead_prices,
    fetch_generation,
    fetch_installed_capacity,
    mock_generation,
    mock_prices,
)
from data.eurostat import (
    fetch_inflation,
    fetch_household_electricity_price,
    fetch_energy_import_dependency,
    entsoe_to_eurostat,
)
from data.processor import (
    price_summary,
    cheapest_hours,
    most_expensive_hours,
    daily_avg_prices,
    total_by_source,
    renewable_share,
    nuclear_share,
    fossil_share,
    low_carbon_share,
    classify_source,
    generation_mix_pct,
    daily_avg_generation,
    top_sources,
    RENEWABLE_SOURCES,
    NUCLEAR_SOURCES,
    FOSSIL_SOURCES,
    TIER_COLORS,
    monthly_avg_prices,
    monthly_renewable_share,
    price_volatility,
)
from data.cache_db import clear_cache, cache_info, cache_stats, db_get_updated_at
from data.scheduler import start_scheduler

# ── Start background scheduler (idempotent — safe on every Streamlit re-run) ──
start_scheduler()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Energy & Economics Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #0f1117 0%, #1a1d2e 100%);
        border: 1px solid #2a2d3e;
        border-radius: 10px;
        padding: 1.1rem 1.4rem;
        text-align: center;
    }
    .metric-card-win {
        background: linear-gradient(135deg, #0d3d1f 0%, #15532a 100%);
        border: 2px solid #22c55e;
        border-radius: 10px;
        padding: 1.1rem 1.4rem;
        text-align: center;
        box-shadow: 0 0 16px rgba(34, 197, 94, 0.25), inset 0 0 24px rgba(34, 197, 94, 0.08);
    }
    .metric-card-win .metric-label { color: #86efac; }
    .metric-card-win .metric-value { color: #ffffff; }
    .metric-card-win .metric-unit  { color: #bbf7d0; }

    .metric-card-loss {
        background: linear-gradient(135deg, #4c0f1a 0%, #611821 100%);
        border: 2px solid #ef4444;
        border-radius: 10px;
        padding: 1.1rem 1.4rem;
        text-align: center;
        box-shadow: 0 0 16px rgba(239, 68, 68, 0.25), inset 0 0 24px rgba(239, 68, 68, 0.08);
    }
    .metric-card-loss .metric-label { color: #fca5a5; }
    .metric-card-loss .metric-value { color: #ffffff; }
    .metric-card-loss .metric-unit  { color: #fecaca; }

    .metric-card-overall {
        background: linear-gradient(135deg, #422006 0%, #713f12 100%);
        border: 2px solid #f59e0b;
        border-radius: 10px;
        padding: 1.1rem 1.4rem;
        text-align: center;
        box-shadow: 0 0 20px rgba(245, 158, 11, 0.3), inset 0 0 24px rgba(245, 158, 11, 0.1);
    }
    .metric-card-overall .metric-label { color: #fcd34d; }
    .metric-card-overall .metric-value { color: #ffffff; }
    .metric-card-overall .metric-unit  { color: #fde68a; }
    .metric-label {
        color: #6b7280;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-family: 'DM Mono', monospace;
    }
    .metric-value {
        color: #e8eaf6;
        font-size: 1.75rem;
        font-weight: 700;
        line-height: 1.2;
        margin: 0.2rem 0;
    }
    .metric-unit {
        color: #4b5563;
        font-size: 0.72rem;
        font-family: 'DM Mono', monospace;
    }
    .metric-delta-pos { color: #34d399; font-size: 0.8rem; }
    .metric-delta-neg { color: #f87171; font-size: 0.8rem; }

    /* Section headers */
    .section-title {
        color: #a5b4fc;
        font-size: 1rem;
        font-weight: 600;
        border-left: 3px solid #6366f1;
        padding-left: 0.6rem;
        margin: 1.8rem 0 0.8rem;
        font-family: 'DM Mono', monospace;
        letter-spacing: 0.02em;
    }

    /* Thesis callout */
    .thesis-box {
        background: linear-gradient(135deg, #1e1b4b 0%, #1a1d2e 100%);
        border: 1px solid #4338ca;
        border-radius: 10px;
        padding: 1rem 1.4rem;
        margin-bottom: 1.2rem;
        font-size: 0.88rem;
        color: #c7d2fe;
        line-height: 1.6;
    }
    .thesis-box strong { color: #a5b4fc; }

    /* Placeholder / coming soon */
    .placeholder-box {
        background: #0f1117;
        border: 1px dashed #374151;
        border-radius: 10px;
        padding: 1.5rem;
        text-align: center;
        color: #4b5563;
        font-family: 'DM Mono', monospace;
        font-size: 0.8rem;
    }
    .placeholder-box span { color: #6366f1; font-weight: 600; }

    /* Disclaimer */
    .disclaimer {
        background: #1c1a12;
        border: 1px solid #78350f;
        border-radius: 8px;
        padding: 0.7rem 1rem;
        color: #fbbf24;
        font-size: 0.78rem;
        font-family: 'DM Mono', monospace;
        margin-bottom: 1rem;
    }

    /* Causal chain */
    .causal-chain {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
        margin: 0.8rem 0;
    }
    .causal-step {
        background: #1e1b4b;
        border: 1px solid #4338ca;
        border-radius: 6px;
        padding: 0.3rem 0.7rem;
        font-size: 0.78rem;
        color: #c7d2fe;
        font-family: 'DM Mono', monospace;
        white-space: nowrap;
    }
    .causal-arrow { color: #6366f1; font-size: 1rem; }

    /* Stale data banner */
    .stale-banner {
        background: linear-gradient(135deg, #3d2000 0%, #4a2800 100%);
        border: 1px solid #f59e0b;
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 0.75rem 1.1rem;
        margin-bottom: 1rem;
        color: #fcd34d;
        font-size: 0.82rem;
        font-family: 'DM Mono', monospace;
        line-height: 1.5;
    }
    .stale-banner strong { color: #fbbf24; }

    /* Pulsing fetch button — applied via JS injection when data is stale */
    @keyframes pulse-border {
        0%   { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7); }
        70%  { box-shadow: 0 0 0 8px rgba(245, 158, 11, 0); }
        100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
    }
    .stale-fetch-btn > div > button {
        animation: pulse-border 1.6s ease-in-out infinite !important;
        border-color: #f59e0b !important;
        color: #fbbf24 !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Tier colour helper ────────────────────────────────────────────────────────
def tier_color(source_name: str) -> str:
    """Return the tier colour (renewable/nuclear/fossil/other) for a source name."""
    return TIER_COLORS[classify_source(source_name)]


# ── Chart height constants ────────────────────────────────────────────────────
CH_SM  = 260   # small — sparklines, supplementary context
CH_MD  = 340   # medium — standard single-metric charts
CH_LG  = 420   # large — primary feature charts, multi-trace comparisons


# ── 2022 energy crisis annotation ────────────────────────────────────────────
_CRISIS_DATE  = "2022-02-24"
_CRISIS_LABEL = "🇺🇦 Feb 2022"

def _add_crisis_line(fig, x_values) -> None:
    """
    Add a vertical reference line at 2022-02-24 (Russia/Ukraine war start)
    if that date falls within the chart's x-axis range.

    Handles all index types used in this app:
      - DatetimeIndex     (prices, generation, monthly aggregates)
      - PeriodIndex       (CPI series before .to_timestamp())
      - Integer years     (installed capacity, import dependency)
      - Semester strings  (household prices: "2020-S1")
    For integer and semester indexes the annotation is skipped — a specific
    date doesn't map cleanly onto annual or bi-annual data.
    """
    try:
        crisis = pd.Timestamp(_CRISIS_DATE)

        # Already a DatetimeIndex — fastest path, no parsing needed
        if isinstance(x_values, pd.DatetimeIndex):
            if x_values.min() <= crisis <= x_values.max():
                fig.add_vline(
                    x=_CRISIS_DATE,
                    line_dash="dot",
                    line_color="rgba(239,68,68,0.5)",
                    line_width=1.5,
                    annotation_text=_CRISIS_LABEL,
                    annotation_position="top left",
                    annotation_font=dict(color="#fca5a5", size=10),
                )
            return

        # Integer index (years) or string semester labels — skip, not meaningful
        vals = list(x_values)
        if not vals:
            return
        if isinstance(vals[0], (int, str)) and (
            isinstance(vals[0], int) or
            (isinstance(vals[0], str) and "-S" in vals[0])
        ):
            return

        # Anything else: try to parse with format='mixed' (no warning)
        dates = pd.to_datetime(vals, format="mixed", dayfirst=False)
        if dates.min() <= crisis <= dates.max():
            fig.add_vline(
                x=_CRISIS_DATE,
                line_dash="dot",
                line_color="rgba(239,68,68,0.5)",
                line_width=1.5,
                annotation_text=_CRISIS_LABEL,
                annotation_position="top left",
                annotation_font=dict(color="#fca5a5", size=10),
            )
    except Exception:
        pass  # never crash a chart over an annotation


# ── Responsive metric columns ─────────────────────────────────────────────────
def _metric_cols(n: int):
    """
    Return n columns for metric cards.
    Caps at 3 on any screen — 4+ columns collapse on mobile and look cramped.
    For n=4 or 5, split into two rows of 2.
    """
    n = min(n, 3)
    return st.columns(n)


def _stale_banner(fetched_country_code: str | None, current_country_code: str,
                  current_label: str, fetched_label: str | None,
                  fetched_start: str | None = None, fetched_end: str | None = None,
                  current_start: str | None = None, current_end: str | None = None) -> str | None:
    """
    Returns HTML for a stale data warning banner, or None if data is current.

    Stale conditions:
      - A different country is selected than what was last fetched
      - The date range has changed since the last fetch (for operational tabs)
    """
    if fetched_country_code is None:
        return None

    country_mismatch = fetched_country_code != current_country_code
    date_mismatch    = (
        fetched_start is not None and current_start is not None and
        (fetched_start != current_start or fetched_end != current_end)
    )

    if not country_mismatch and not date_mismatch:
        return None

    if country_mismatch:
        msg = (
            f"⚠️ <strong>Data shown is for {fetched_label or fetched_country_code}</strong> — "
            f"you've selected <strong>{current_label}</strong>. "
            f"Click <strong>Fetch Data</strong> to load the new country."
        )
    else:
        msg = (
            f"⚠️ <strong>Date range has changed</strong> — "
            f"data shown is for <strong>{fetched_start} → {fetched_end}</strong>. "
            f"Click <strong>Fetch Data</strong> to update."
        )
    return f'<div class="stale-banner">{msg}</div>'


def _last_updated(fn_name: str, *args, **kwargs) -> str:
    """
    Return a human-readable 'last updated' string for a cached dataset.
    Shows e.g. 'Last updated: today at 14:32' or 'Last updated: 2 days ago'.
    """
    import time as _time
    from datetime import datetime as _dt
    ts = db_get_updated_at(fn_name, *args, **kwargs)
    if ts is None:
        return ""
    age_s = _time.time() - ts
    dt    = _dt.fromtimestamp(ts)
    if age_s < 3600:
        label = f"{int(age_s // 60)} min ago"
    elif age_s < 86400:
        label = f"today at {dt.strftime('%H:%M')}"
    elif age_s < 172800:
        label = f"yesterday at {dt.strftime('%H:%M')}"
    else:
        label = dt.strftime("%d %b %Y %H:%M")
    return f"<span style='font-size:0.68rem; color:#4b5563; font-family:DM Mono,monospace'>⏱ Last fetched: {label}</span>"


# ── Comparison card helper ────────────────────────────────────────────────────
def cmp_card(label: str, value: str, unit: str, result: str = "neutral") -> str:
    """
    Return an HTML metric card for the comparison tab.

    result:
        'win'     → green border  (better outcome for this country)
        'loss'    → red border    (worse outcome for this country)
        'neutral' → default card  (winner/loser summary card)
    """
    css_class = {
        "win":     "metric-card-win",
        "loss":    "metric-card-loss",
        "overall": "metric-card-overall",
        "neutral": "metric-card",
    }.get(result, "metric-card")
    return f"""
    <div class="{css_class}">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-unit">{unit}</div>
    </div>"""


# ── Countries ─────────────────────────────────────────────────────────────────
COUNTRIES = {
    # Tier 1 — Most reliable
    "Germany (DE-LU zone)":  "DE_LU",
    "France":                "FR",
    "Belgium":               "BE",
    "Netherlands":           "NL",
    "Spain":                 "ES",
    "Portugal":              "PT",
    "Poland":                "PL",
    "Czech Republic":        "CZ",
    "Hungary":               "HU",
    "Romania":               "RO",
    # Tier 2 — Usually works
    "Austria":               "AT",
    "Switzerland":           "CH",
    "Denmark (West, DK-1)":  "DK",    # prices use DK_1 zone automatically
    "Finland":               "FI",
    "Greece":                "GR",
    "Slovakia":              "SK",
    "Slovenia":              "SI",
    "Bulgaria":              "BG",
    "Croatia":               "HR",
    "Latvia":                "LV",
    "Lithuania":             "LT",
    # Tier 3 — Partial
    "Italy (North)":         "IT_NORD",  # correct entsoe-py code (was IT_NORTH)
    "Sweden (SE3)":          "SE_3",
    "Norway":                "NO",
    "Great Britain":         "GB",
}

# ── URL params → sidebar default index ────────────────────────────────────────
# Computed here (after COUNTRIES, before sidebar) so the selectbox can use it.
# Only applied on first load — once the user has clicked Fetch, the sidebar
# selection always wins and the URL is updated to match.
_qp          = st.query_params
_first_load  = not st.session_state.get("fetch_attempted", False)
_default_idx = 0

if _first_load and "country" in _qp:
    _code    = _qp.get("country", "")
    _matched = [k for k, v in COUNTRIES.items() if v == _code]
    if _matched:
        _default_idx = list(COUNTRIES.keys()).index(_matched[0])


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ Energy & Economics")
    st.caption("ENTSO-E · Eurostat · Public & Academic Dashboard")
    st.divider()

    # Primary country — index comes from URL params on first load, 0 otherwise
    country_label = st.selectbox("🌍 Primary country", list(COUNTRIES.keys()),
                                 index=_default_idx)
    country_code  = COUNTRIES[country_label]

    st.divider()

    # Comparison toggle
    st.markdown("**🔀 Compare with**")
    compare_enabled = st.toggle("Enable comparison", value=False)
    if compare_enabled:
        compare_options = {k: v for k, v in COUNTRIES.items() if k != country_label}
        compare_label   = st.selectbox("🌍 Compare country", list(compare_options.keys()), index=0)
        compare_code    = compare_options[compare_label]
    else:
        compare_label = compare_code = None

    st.divider()

    # Date range (operational/medium-term)
    st.markdown("**📅 Short/Medium-term range**")
    st.caption("Used in tabs 2 & 3")
    today     = date.today()
    default_s = today - timedelta(days=30)
    default_e = today - timedelta(days=1)

    start_date = st.date_input("Start date", value=default_s,
                               min_value=date(2015, 1, 1), max_value=today)
    end_date   = st.date_input("End date",   value=default_e,
                               min_value=date(2015, 1, 1), max_value=today)

    if start_date >= end_date:
        st.error("End date must be after start date.")
        st.stop()

    st.divider()

    # Long-term year range
    st.markdown("**📅 Long-term range**")
    st.caption("Used in tab 1")
    long_term_years = st.slider("Years of history", min_value=3, max_value=10, value=5)

    st.divider()

    # Detect staleness to decide whether to pulse the button
    _fetched_cc  = st.session_state.get("fetched_country")
    _is_stale    = (
        _fetched_cc is not None and (
            _fetched_cc != country_code or
            st.session_state.get("fetched_start") != str(start_date) or
            st.session_state.get("fetched_end")   != str(end_date)
        )
    )

    if _is_stale:
        st.markdown('<div class="stale-fetch-btn">', unsafe_allow_html=True)
    fetch_btn = st.button("🔄 Fetch Data", width='stretch', type="primary")
    if _is_stale:
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption("⚠️ Selection changed — refetch needed")

    st.divider()
    st.markdown("""
    <div style='font-size:0.72rem; color:#4b5563; font-family: DM Mono, monospace; line-height:1.6'>
    <strong style='color:#6366f1'>Data sources</strong><br>
    ENTSO-E Transparency Platform<br>
    Eurostat HICP<br><br>
    <strong style='color:#6366f1'>Limitations</strong><br>
    Installed capacity data may be incomplete for some countries.<br>
    CPI is influenced by many factors beyond energy.
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    with st.expander("🗄️ Cache & Scheduler"):
        stats = cache_stats()
        st.markdown(
            f"<div style='font-size:0.72rem; font-family:DM Mono,monospace; line-height:2; color:#9ca3af;'>"
            f"<span style='color:#22c55e'>●</span> <strong>{stats['fresh']}</strong> fresh &nbsp;·&nbsp; "
            f"<strong>{stats['total']}</strong> total entries &nbsp;·&nbsp; "
            f"<strong>{stats['size_kb']} KB</strong>"
            f"</div>",
            unsafe_allow_html=True,
        )
        entries = cache_info()
        if entries:
            with st.expander(f"Show {len(entries)} entries"):
                for e in entries:
                    colour = "#22c55e" if e["fresh"] else "#f59e0b"
                    st.markdown(
                        f"<div style='font-size:0.68rem; font-family:DM Mono,monospace; color:{colour}'>"
                        f"{'●' if e['fresh'] else '○'} {e['key']} &nbsp; "
                        f"{e['age_min']} min ago &nbsp;·&nbsp; {e['size_kb']} KB &nbsp;·&nbsp; TTL {e['ttl_h']}h"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        st.caption("🤖 Background scheduler pre-fetches top countries every 2h.")
        if st.button("🗑 Clear all cache", width='stretch', key="btn_clear_cache"):
            n = clear_cache()
            st.success(f"Cleared {n} entries.")



# ── Session state ─────────────────────────────────────────────────────────────
_keys = [
    "prices", "gen", "inflation", "capacity",
    "household_price", "import_dep",
    "cmp_prices", "cmp_gen", "cmp_inflation", "cmp_capacity",
    "cmp_household_price", "cmp_import_dep",
    "last_country", "last_cmp_country", "last_n_years",
    "fetch_attempted",
    "fetched_country", "fetched_cmp_country",
    "fetched_start", "fetched_end",
]
for k in _keys:
    if k not in st.session_state:
        st.session_state[k] = None


# ── Data fetching ─────────────────────────────────────────────────────────────
if fetch_btn:
    st.session_state.fetch_attempted = True
    # Update URL params so this view can be shared/bookmarked
    new_params = {
        "country": country_code,
        "years":   str(long_term_years),
        "start":   str(start_date),
        "end":     str(end_date),
    }
    if compare_enabled and compare_code:
        new_params["compare"] = compare_code
    st.query_params.update(new_params)
    # Record what was fetched so stale detection works correctly
    st.session_state.fetched_country       = country_code
    st.session_state.fetched_country_label = country_label
    st.session_state.fetched_cmp_country   = compare_code if compare_enabled else None
    st.session_state.fetched_cmp_label     = compare_label if compare_enabled else None
    st.session_state.fetched_start         = str(start_date)
    st.session_state.fetched_end           = str(end_date)
    ts_start = pd.Timestamp(start_date)
    ts_end   = pd.Timestamp(end_date) + pd.Timedelta(days=1)

    # --- Primary country ---
    with st.spinner(f"Fetching ENTSO-E data for {country_label}…"):
        try:
            st.session_state.prices = fetch_day_ahead_prices(country_code, ts_start, ts_end)
        except Exception as e:
            st.warning(f"Prices unavailable: {e}")
            st.session_state.prices = None

        try:
            st.session_state.gen = fetch_generation(country_code, ts_start, ts_end)
        except Exception as e:
            st.warning(f"Generation data unavailable: {e}")
            st.session_state.gen = None

        try:
            st.session_state.capacity = fetch_installed_capacity(
                country_code, long_term_years
            )
        except Exception as e:
            st.warning(f"Installed capacity unavailable for {country_label}: {e}")
            st.session_state.capacity = None

    _eurostat_stale = (
        st.session_state.last_country != country_code or
        st.session_state.get("last_primary_n_years") != long_term_years
    )
    if _eurostat_stale:
        with st.spinner("Fetching Eurostat inflation data…"):
            try:
                st.session_state.inflation    = fetch_inflation(country_code, n_years=long_term_years)
                st.session_state.last_country = country_code
                st.session_state["last_primary_n_years"] = long_term_years
            except Exception as e:
                st.warning(f"Inflation data unavailable: {e}")
                st.session_state.inflation = None

        with st.spinner("Fetching Eurostat household electricity prices…"):
            try:
                st.session_state.household_price = fetch_household_electricity_price(
                    country_code, n_years=long_term_years
                )
            except Exception as e:
                st.warning(f"Household electricity prices unavailable: {e}")
                st.session_state.household_price = None

        with st.spinner("Fetching Eurostat energy import dependency…"):
            try:
                st.session_state.import_dep = fetch_energy_import_dependency(
                    country_code, n_years=long_term_years
                )
            except Exception as e:
                st.warning(f"Energy import dependency unavailable: {e}")
                st.session_state.import_dep = None

    # --- Compare country ---
    if compare_enabled and compare_code:
        with st.spinner(f"Fetching ENTSO-E data for {compare_label}…"):
            try:
                st.session_state.cmp_prices = fetch_day_ahead_prices(compare_code, ts_start, ts_end)
            except Exception as e:
                st.warning(f"Prices unavailable for {compare_label}: {e}")
                st.session_state.cmp_prices = None

            try:
                st.session_state.cmp_gen = fetch_generation(compare_code, ts_start, ts_end)
            except Exception as e:
                st.warning(f"Generation unavailable for {compare_label}: {e}")
                st.session_state.cmp_gen = None

            try:
                st.session_state.cmp_capacity = fetch_installed_capacity(
                    compare_code, long_term_years
                )
            except Exception as e:
                st.warning(f"Installed capacity unavailable for {compare_label}: {e}")
                st.session_state.cmp_capacity = None

        # Eurostat data for comparison country: re-fetch if country OR n_years changed.
        # Uses a separate last_cmp_n_years key so primary and comparison country
        # n_years tracking don't interfere with each other.
        _cmp_eurostat_stale = (
            st.session_state.last_cmp_country != compare_code or
            st.session_state.get("last_cmp_n_years") != long_term_years
        )
        if _cmp_eurostat_stale:
            with st.spinner(f"Fetching Eurostat data for {compare_label}…"):
                try:
                    st.session_state.cmp_inflation    = fetch_inflation(compare_code, n_years=long_term_years)
                    st.session_state.last_cmp_country = compare_code
                    st.session_state["last_cmp_n_years"] = long_term_years
                except Exception as e:
                    st.warning(f"Inflation unavailable for {compare_label}: {e}")
                    st.session_state.cmp_inflation = None

                try:
                    st.session_state.cmp_household_price = fetch_household_electricity_price(
                        compare_code, n_years=long_term_years
                    )
                except Exception as e:
                    st.warning(f"Household prices unavailable for {compare_label}: {e}")
                    st.session_state.cmp_household_price = None

                try:
                    st.session_state.cmp_import_dep = fetch_energy_import_dependency(
                        compare_code, n_years=long_term_years
                    )
                except Exception as e:
                    st.warning(f"Import dependency unavailable for {compare_label}: {e}")
                    st.session_state.cmp_import_dep = None
    else:
        st.session_state.cmp_prices        = None
        st.session_state.cmp_gen           = None
        st.session_state.cmp_inflation     = None
        st.session_state.cmp_capacity      = None
        st.session_state.cmp_household_price = None
        st.session_state.cmp_import_dep    = None
        st.session_state.last_cmp_country  = None

# ── Unpack session state ───────────────────────────────────────────────────────
prices              = st.session_state.prices
gen                 = st.session_state.gen
inflation           = st.session_state.inflation
capacity            = st.session_state.capacity
household_price     = st.session_state.household_price
import_dep          = st.session_state.import_dep
cmp_prices          = st.session_state.cmp_prices
cmp_gen             = st.session_state.cmp_gen
cmp_inflation       = st.session_state.cmp_inflation
cmp_capacity        = st.session_state.cmp_capacity
cmp_household_price = st.session_state.cmp_household_price
cmp_import_dep      = st.session_state.cmp_import_dep

# ── Empty state ───────────────────────────────────────────────────────────────
fetch_attempted = st.session_state.fetch_attempted
if all(v is None for v in [prices, gen, inflation, capacity]):
    st.markdown("## ⚡ Energy & Economics Dashboard")

    if fetch_attempted:
        st.error(
            f"All data sources failed for **{country_label}**. "
            "This may be a temporary ENTSO-E outage (503) or the country has limited API coverage. "
            "Try a different country or date range, or check the warnings above."
        )

    st.markdown("""
    <div class="thesis-box">
    <strong>Research thesis:</strong> Countries that invested in renewable energy reduced their dependence
    on imported fossil fuels — leading to more stable electricity prices, lower energy inflation,
    and more resilient economies.<br><br>
    Select a country in the sidebar and click <strong>Fetch Data</strong> to begin.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="causal-chain">
        <span class="causal-step">🔋 Renewable investment</span>
        <span class="causal-arrow">→</span>
        <span class="causal-step">📉 Less fossil imports</span>
        <span class="causal-arrow">→</span>
        <span class="causal-step">🛡️ Lower price exposure</span>
        <span class="causal-arrow">→</span>
        <span class="causal-step">⚡ Stable electricity prices</span>
        <span class="causal-arrow">→</span>
        <span class="causal-step">📊 Lower energy CPI</span>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Quick-start suggestions ────────────────────────────────────────────────
    st.markdown("#### 💡 Suggested comparisons to get started")
    st.caption("These pairings illustrate the thesis clearly — click one to pre-fill the sidebar, then hit Fetch Data.")

    SUGGESTIONS = [
        {
            "label":   "🌬️ Denmark vs Poland",
            "subtitle": "Wind leader vs coal-heavy economy",
            "detail":  "Denmark has one of the highest renewable shares in Europe. Poland relies heavily on coal. A striking contrast in import dependency and energy CPI.",
            "country": "DK",
            "compare": "PL",
        },
        {
            "label":   "⚛️ France vs Germany",
            "subtitle": "Nuclear stability vs renewable transition",
            "detail":  "France's nuclear fleet gives it low import dependency despite minimal renewables. Germany is mid-transition. Great case for the nuclear discussion.",
            "country": "FR",
            "compare": "DE_LU",
        },
        {
            "label":   "☀️ Spain vs Czech Republic",
            "subtitle": "Southern renewables vs Central European fossil mix",
            "detail":  "Spain has invested heavily in solar and wind. Czech Republic still relies on coal and gas. Compare their household prices and energy CPI.",
            "country": "ES",
            "compare": "CZ",
        },
        {
            "label":   "🇦🇹 Austria vs Belgium",
            "subtitle": "Hydro-rich vs mixed energy mix",
            "detail":  "Austria generates most electricity from hydro. Belgium uses nuclear + gas. Both have low fossil exposure but via different routes.",
            "country": "AT",
            "compare": "BE",
        },
    ]

    col_pairs = [st.columns(2), st.columns(2)]
    for i, sug in enumerate(SUGGESTIONS):
        row, col = i // 2, i % 2
        with col_pairs[row][col]:
            st.markdown(f"""
            <div style='background:linear-gradient(135deg,#0f1117 0%,#1a1d2e 100%);
                        border:1px solid #2a2d3e; border-radius:10px;
                        padding:1rem 1.2rem; height:100%;'>
                <div style='font-size:1rem; font-weight:700; color:#e8eaf6;
                            margin-bottom:0.2rem;'>{sug["label"]}</div>
                <div style='font-size:0.78rem; color:#6366f1; font-family:DM Mono,monospace;
                            margin-bottom:0.5rem;'>{sug["subtitle"]}</div>
                <div style='font-size:0.8rem; color:#9ca3af; line-height:1.5;'>{sug["detail"]}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Use this comparison", key=f"quick_{sug['country']}_{sug['compare']}"):
                st.query_params.update({
                    "country": sug["country"],
                    "compare": sug["compare"],
                    "years":   "5",
                })
                st.rerun()

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌍 Structural View",
    "📈 Market Dynamics",
    "⚡ Operational View",
    "🔀 Country Comparison",
    "📚 Sources & Data",
    "❓ How to Use",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — STRUCTURAL VIEW  (Long-term, 5–10 years)
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    _b = _stale_banner(
        st.session_state.get("fetched_country"), country_code,
        country_label, st.session_state.get("fetched_country_label"),
    )
    if _b: st.markdown(_b, unsafe_allow_html=True)
    st.markdown(f"### 🌍 Structural View — {country_label}")
    st.markdown("""
    <div class="thesis-box">
    <strong>What this tab shows:</strong> Has this country actually committed to renewables?
    Installed capacity and long-term CPI trends reveal structural investment — not just what
    the weather happened to produce last week.
    </div>
    """, unsafe_allow_html=True)

    # ── Installed capacity ─────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🔋 Installed Generation Capacity (MW)</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="disclaimer">
    ⚠️ Installed capacity data quality varies by country on ENTSO-E.
    Missing or incomplete data is shown as a warning — it does not necessarily mean
    the country has no renewable capacity.
    </div>
    """, unsafe_allow_html=True)

    if capacity is not None and not capacity.empty:
        renewable_cap_cols = [c for c in capacity.columns if c in RENEWABLE_SOURCES]
        nuclear_cap_cols   = [c for c in capacity.columns if c in NUCLEAR_SOURCES]
        fossil_cap_cols    = [c for c in capacity.columns if c in FOSSIL_SOURCES]
        other_cap_cols     = [c for c in capacity.columns
                              if c not in RENEWABLE_SOURCES
                              and c not in NUCLEAR_SOURCES
                              and c not in FOSSIL_SOURCES]

        # Renewable and nuclear share of installed capacity over time
        if renewable_cap_cols or nuclear_cap_cols:
            cap_total    = capacity.sum(axis=1)
            cap_re       = capacity[renewable_cap_cols].sum(axis=1) if renewable_cap_cols else cap_total * 0
            cap_nu       = capacity[nuclear_cap_cols].sum(axis=1)   if nuclear_cap_cols   else cap_total * 0
            cap_re_share = (cap_re / cap_total * 100).round(1)
            cap_nu_share = (cap_nu / cap_total * 100).round(1)
            cap_lc_share = ((cap_re + cap_nu) / cap_total * 100).round(1)

            latest_cap_share = cap_re_share.iloc[-1] if len(cap_re_share) > 0 else None
            latest_nu_share  = cap_nu_share.iloc[-1] if len(cap_nu_share) > 0 else None

            c1, c2, c3, c4 = st.columns(4)
            if latest_cap_share is not None:
                c1.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Renewable Capacity Share</div>
                    <div class="metric-value">{latest_cap_share:.1f}%</div>
                    <div class="metric-unit">of total · latest year</div>
                </div>""", unsafe_allow_html=True)

            if latest_nu_share is not None and latest_nu_share > 0:
                c2.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Nuclear Capacity Share</div>
                    <div class="metric-value">{latest_nu_share:.1f}%</div>
                    <div class="metric-unit">low-carbon, imported fuel</div>
                </div>""", unsafe_allow_html=True)

            total_re_gw = round(cap_re.iloc[-1] / 1000, 1) if len(cap_re) > 0 else None
            if total_re_gw is not None:
                c3.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Total Renewable Capacity</div>
                    <div class="metric-value">{total_re_gw} GW</div>
                    <div class="metric-unit">installed · latest year</div>
                </div>""", unsafe_allow_html=True)

            if len(cap_re_share) >= 2:
                growth = round(cap_re_share.iloc[-1] - cap_re_share.iloc[0], 1)
                sign   = "+" if growth >= 0 else ""
                c4.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Renewable Share Growth</div>
                    <div class="metric-value">{sign}{growth}pp</div>
                    <div class="metric-unit">over {long_term_years} years</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("")

            # Trend lines: renewable share + nuclear share + combined low-carbon
            fig_share = go.Figure()
            fig_share.add_trace(go.Scatter(
                x=cap_re_share.index, y=cap_re_share.values,
                name="🌱 Renewable",
                line=dict(color=TIER_COLORS["renewable"], width=3),
                fill="tozeroy", fillcolor=f"rgba(34,197,94,0.08)",
                mode="lines+markers", marker=dict(size=6),
            ))
            if cap_nu_share.max() > 0:
                fig_share.add_trace(go.Scatter(
                    x=cap_nu_share.index, y=cap_nu_share.values,
                    name="⚛️ Nuclear",
                    line=dict(color=TIER_COLORS["nuclear"], width=2, dash="dot"),
                    mode="lines+markers", marker=dict(size=5),
                ))
                fig_share.add_trace(go.Scatter(
                    x=cap_lc_share.index, y=cap_lc_share.values,
                    name="🔵 Low-carbon (renewable + nuclear)",
                    line=dict(color="#818cf8", width=1.5, dash="dash"),
                    mode="lines",
                ))
            fig_share.update_layout(
                title=f"Renewable & Nuclear Share of Installed Capacity — {country_label} (%)",
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                yaxis=dict(title="%", range=[0, 105]),
                xaxis_title="Year",
                legend=dict(orientation="h", y=-0.2),
            )
            _add_crisis_line(fig_share, cap_re_share.index)
            st.plotly_chart(fig_share, width='stretch')

            # Stacked area: capacity by source over time, ordered by tier
            ordered = renewable_cap_cols + nuclear_cap_cols + fossil_cap_cols + other_cap_cols
            color_map = {c: tier_color(c) for c in ordered}
            fig_cap = px.area(
                capacity[ordered],
                title=f"Installed Capacity by Source — {country_label} (MW)",
                labels={"value": "MW", "index": "Year", "variable": "Source"},
                color_discrete_map=color_map,
            )
            fig_cap.update_layout(
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0), height=CH_LG,
                legend=dict(orientation="h", y=-0.25),
            )
            st.plotly_chart(fig_cap, width='stretch')

    else:
        st.info(
            "Installed capacity data could not be loaded for this country. "
            "Try fetching again, or select a different country. "
            "Household electricity prices and import dependency are shown below regardless."
        )

    # ── Long-term inflation ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 Long-term Inflation Trend</div>', unsafe_allow_html=True)

    if inflation is not None:
        cpi_s    = inflation["cpi"]
        energy_s = inflation["energy"]

        i1, i2, i3 = st.columns(3)
        i1.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Latest General CPI</div>
            <div class="metric-value">{inflation['latest_cpi']:+.1f}%</div>
            <div class="metric-unit">YoY · {str(cpi_s.index[-1])}</div>
        </div>""", unsafe_allow_html=True)
        i2.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Latest Energy CPI</div>
            <div class="metric-value">{inflation['latest_energy']:+.1f}%</div>
            <div class="metric-unit">YoY · {str(energy_s.index[-1])}</div>
        </div>""", unsafe_allow_html=True)
        spread = round(inflation["latest_energy"] - inflation["latest_cpi"], 2)
        i3.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Energy vs General Spread</div>
            <div class="metric-value">{spread:+.1f}pp</div>
            <div class="metric-unit">energy − general CPI</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("")

        fig_inf = go.Figure()
        fig_inf.add_trace(go.Scatter(
            x=cpi_s.index.to_timestamp(), y=cpi_s.values,
            name="General CPI", line=dict(color="#6366f1", width=2),
        ))
        fig_inf.add_trace(go.Scatter(
            x=energy_s.index.to_timestamp(), y=energy_s.values,
            name="Energy & Housing CPI", line=dict(color="#f59e0b", width=2, dash="dot"),
        ))
        fig_inf.add_hline(y=2, line_dash="dot", line_color="#374151", line_width=1,
                          annotation_text="ECB 2% target", annotation_position="bottom right")
        fig_inf.add_hline(y=0, line_dash="dash", line_color="#374151", line_width=1)
        fig_inf.update_layout(
            title=f"Inflation — {country_label} · {long_term_years}-year view (% YoY)",
            template="plotly_dark",
            margin=dict(l=0, r=0, t=40, b=0), height=CH_LG,
            yaxis_title="Annual rate of change (%)",
            legend=dict(orientation="h", y=-0.15),
        )
        _add_crisis_line(fig_inf, cpi_s.index.to_timestamp())
        st.plotly_chart(fig_inf, width='stretch')
        st.markdown(_last_updated("fetch_inflation", country_code, n_years=long_term_years), unsafe_allow_html=True)
        with st.expander("📋 Last 12 months of inflation data"):
            last12 = pd.DataFrame({
                "Month":         [str(p) for p in cpi_s.index[-12:]],
                "General CPI %": cpi_s.values[-12:].round(2),
                "Energy CPI %":  energy_s.reindex(cpi_s.index[-12:]).values.round(2),
            })
            st.dataframe(last12, hide_index=True, width='stretch')
    else:
        if fetch_attempted:
            st.warning("Inflation data could not be loaded — Eurostat may be temporarily unavailable.")
        else:
            st.info("Click **Fetch Data** to load inflation data.")

    # ── Household electricity prices ───────────────────────────────────────────
    st.markdown('<div class="section-title">🔌 Household Electricity Prices</div>', unsafe_allow_html=True)
    st.caption("Source: Eurostat nrg_pc_204 · Bi-annual · Excluding taxes for cross-country comparability · Consumption band varies by country (DE/FR use 1000–2499 kWh, AT/BE use <1000 kWh, others use 2500–4999 kWh)")

    if household_price is not None and len(household_price) > 0:
        latest_hp  = household_price.iloc[-1]
        oldest_hp  = household_price.iloc[0]
        change_hp  = round(latest_hp - oldest_hp, 4)
        change_pct = round((change_hp / oldest_hp) * 100, 1) if oldest_hp != 0 else 0.0
        sign       = "+" if change_pct >= 0 else ""

        h1, h2, h3 = st.columns(3)
        h1.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Latest Price (excl. taxes)</div>
            <div class="metric-value">{latest_hp:.4f}</div>
            <div class="metric-unit">€/kWh · {household_price.index[-1]}</div>
        </div>""", unsafe_allow_html=True)
        h2.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Change over period</div>
            <div class="metric-value">{sign}{change_pct}%</div>
            <div class="metric-unit">vs {household_price.index[0]}</div>
        </div>""", unsafe_allow_html=True)
        h3.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Absolute Change</div>
            <div class="metric-value">{sign}{change_hp:.4f}</div>
            <div class="metric-unit">€/kWh over period</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("")

        fig_hp = go.Figure()
        fig_hp.add_trace(go.Scatter(
            x=household_price.index,
            y=household_price.values,
            mode="lines+markers",
            line=dict(color="#6366f1", width=2),
            marker=dict(size=7),
            name="Household price (excl. taxes)",
            hovertemplate="%{x}<br>%{y:.4f} €/kWh<extra></extra>",
        ))
        fig_hp.update_layout(
            title=f"Household Electricity Price — {country_label} (€/kWh, excl. taxes)",
            template="plotly_dark", showlegend=False,
            margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
            yaxis_title="€/kWh",
            xaxis_title="Semester",
        )
        _add_crisis_line(fig_hp, household_price.index)
        st.plotly_chart(fig_hp, width='stretch')
        st.markdown(_last_updated("fetch_household_electricity_price", country_code, n_years=long_term_years), unsafe_allow_html=True)

        with st.expander("📋 Full price table"):
            hp_df = pd.DataFrame({
                "Semester": household_price.index,
                "Price (€/kWh, excl. taxes)": household_price.values.round(4),
            })
            st.dataframe(hp_df, hide_index=True, width='stretch')
    else:
        st.info("Household electricity price data unavailable for this country. "
                "Not all countries report to Eurostat nrg_pc_204 (notably Switzerland, Norway, and some non-EU states).")

    # ── Energy import dependency ───────────────────────────────────────────────
    st.markdown('<div class="section-title">🛢️ Energy Import Dependency</div>', unsafe_allow_html=True)
    st.caption("Source: Eurostat nrg_ind_id · Annual · All energy products combined · "
               "Positive = net importer · Negative = net exporter")

    if import_dep is not None and len(import_dep) > 0:
        latest_id  = import_dep.iloc[-1]
        oldest_id  = import_dep.iloc[0]
        trend_id   = round(latest_id - oldest_id, 1)
        trend_sign = "+" if trend_id >= 0 else ""
        trend_label = "↑ More dependent" if trend_id > 0 else "↓ Less dependent"

        d1, d2, d3 = st.columns(3)
        d1.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Latest Import Dependency</div>
            <div class="metric-value">{latest_id:.1f}%</div>
            <div class="metric-unit">of total energy · {import_dep.index[-1]}</div>
        </div>""", unsafe_allow_html=True)
        d2.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Change over period</div>
            <div class="metric-value">{trend_sign}{trend_id}pp</div>
            <div class="metric-unit">{trend_label} vs {import_dep.index[0]}</div>
        </div>""", unsafe_allow_html=True)

        # Is the country above or below EU average? (~55% in recent years)
        eu_avg_approx = 55.0
        vs_eu = round(latest_id - eu_avg_approx, 1)
        vs_sign = "+" if vs_eu >= 0 else ""
        d3.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">vs EU Average (~55%)</div>
            <div class="metric-value">{vs_sign}{vs_eu}pp</div>
            <div class="metric-unit">{"above" if vs_eu >= 0 else "below"} EU avg</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("")

        fig_id = go.Figure()
        fig_id.add_trace(go.Scatter(
            x=import_dep.index,
            y=import_dep.values,
            mode="lines+markers",
            line=dict(color="#f59e0b", width=2),
            marker=dict(size=6),
            fill="tozeroy",
            fillcolor="rgba(245,158,11,0.08)",
            name="Import dependency",
            hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
        ))
        fig_id.add_hline(
            y=0, line_dash="dash", line_color="#374151", line_width=1,
            annotation_text="Net exporter threshold",
            annotation_position="bottom right",
        )
        fig_id.add_hline(
            y=eu_avg_approx, line_dash="dot", line_color="#4b5563", line_width=1,
            annotation_text="~EU average (55%)",
            annotation_position="top right",
        )
        fig_id.update_layout(
            title=f"Energy Import Dependency — {country_label} (% of total energy)",
            template="plotly_dark", showlegend=False,
            margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
            yaxis_title="%",
            xaxis_title="Year",
        )
        _add_crisis_line(fig_id, import_dep.index)
        st.plotly_chart(fig_id, width='stretch')
    else:
        st.info("Energy import dependency data unavailable for this country.")

    # ── CSV Downloads ──────────────────────────────────────────────────────
    has_any_structural = any([
        capacity is not None and not capacity.empty,
        household_price is not None and len(household_price) > 0,
        import_dep is not None and len(import_dep) > 0,
        inflation is not None,
    ])
    if has_any_structural:
        st.divider()
        st.markdown('<div class="section-title">⬇️ Download Data</div>', unsafe_allow_html=True)
        dl1, dl2 = st.columns(2)
        dl3, dl4 = st.columns(2)

        if capacity is not None and not capacity.empty:
            dl1.download_button(
                "📥 Installed Capacity (CSV)",
                capacity.to_csv(),
                file_name=f"{country_code}_installed_capacity.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t1_capacity",
            )
        if household_price is not None and len(household_price) > 0:
            csv_hp = pd.DataFrame({
                "Semester": household_price.index,
                "Price_EUR_kWh_excl_tax": household_price.values,
            })
            dl2.download_button(
                "📥 Household Prices (CSV)",
                csv_hp.to_csv(index=False),
                file_name=f"{country_code}_household_prices.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t1_household",
            )
        if import_dep is not None and len(import_dep) > 0:
            csv_id = pd.DataFrame({
                "Year": import_dep.index,
                "Import_Dependency_Pct": import_dep.values,
            })
            dl3.download_button(
                "📥 Import Dependency (CSV)",
                csv_id.to_csv(index=False),
                file_name=f"{country_code}_import_dependency.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t1_import_dep",
            )
        if inflation is not None:
            csv_inf = pd.DataFrame({
                "Month": [str(p) for p in inflation["cpi"].index],
                "General_CPI_YoY_Pct": inflation["cpi"].values,
                "Energy_CPI_YoY_Pct":  inflation["energy"].reindex(inflation["cpi"].index).values,
            })
            dl4.download_button(
                "📥 Inflation (CSV)",
                csv_inf.to_csv(index=False),
                file_name=f"{country_code}_inflation.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t1_inflation",
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MARKET DYNAMICS  (Medium-term, 1–2 years)
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    _b = _stale_banner(
        st.session_state.get("fetched_country"), country_code,
        country_label, st.session_state.get("fetched_country_label"),
        st.session_state.get("fetched_start"), st.session_state.get("fetched_end"),
        str(start_date), str(end_date),
    )
    if _b: st.markdown(_b, unsafe_allow_html=True)
    st.markdown(f"### 📈 Market Dynamics — {country_label}")
    st.markdown("""
    <div class="thesis-box">
    <strong>What this tab shows:</strong> Monthly electricity prices alongside renewable generation share
    and CPI inflation. In months with high renewable output, prices tend to be lower and more stable
    — the market reflects the structural investment shown in Tab 1.
    </div>
    """, unsafe_allow_html=True)

    if prices is None and gen is None:
        if fetch_attempted:
            st.warning("Market data could not be loaded — ENTSO-E may be temporarily unavailable (503). Try again shortly.")
        else:
            st.info("Click **Fetch Data** to load market data. For meaningful trends, use a date range of at least 3–6 months.")
    else:
        # ── Monthly price trend ────────────────────────────────────────────────
        if prices is not None and len(prices) > 0:
            st.markdown('<div class="section-title">💶 Monthly Average Day-Ahead Prices</div>', unsafe_allow_html=True)

            monthly_p = monthly_avg_prices(prices)
            vol       = price_volatility(prices)

            p1, p2, p3 = st.columns(3)
            p1.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Average Price</div>
                <div class="metric-value">{round(prices.mean(), 1)}</div>
                <div class="metric-unit">€/MWh · selected period</div>
            </div>""", unsafe_allow_html=True)
            p2.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Price Volatility (Std Dev)</div>
                <div class="metric-value">{vol}</div>
                <div class="metric-unit">€/MWh · lower = more stable</div>
            </div>""", unsafe_allow_html=True)
            stats = price_summary(prices)
            p3.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Price Range</div>
                <div class="metric-value">{stats['min']}–{stats['max']}</div>
                <div class="metric-unit">€/MWh · min to max</div>
            </div>""", unsafe_allow_html=True)

            st.markdown("")

            if len(monthly_p) > 1:
                fig_mp = go.Figure()
                fig_mp.add_trace(go.Bar(
                    x=monthly_p.index.astype(str), y=monthly_p.values,
                    marker_color="#6366f1", name="Monthly avg",
                ))
                fig_mp.update_layout(
                    title=f"Monthly Average Day-Ahead Price — {country_label} (€/MWh)",
                    template="plotly_dark", showlegend=False,
                    margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                    yaxis_title="€/MWh",
                )
                _add_crisis_line(fig_mp, monthly_p.index)
                st.plotly_chart(fig_mp, width='stretch')
            else:
                # Fall back to daily for short ranges
                daily = daily_avg_prices(prices)
                fig_daily = px.bar(
                    daily, title=f"Daily Average Price — {country_label} (€/MWh)",
                    labels={"value": "€/MWh", "index": ""},
                    color_discrete_sequence=["#6366f1"],
                )
                fig_daily.update_layout(
                    template="plotly_dark", showlegend=False,
                    margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                )
                st.plotly_chart(fig_daily, width='stretch')

        # ── Monthly renewable generation share ─────────────────────────────────
        if gen is not None and len(gen) > 0:
            st.markdown('<div class="section-title">🌱 Monthly Renewable Generation Share</div>', unsafe_allow_html=True)

            monthly_re = monthly_renewable_share(gen)

            if len(monthly_re) > 1:
                fig_mre = go.Figure()
                fig_mre.add_trace(go.Scatter(
                    x=monthly_re.index.astype(str), y=monthly_re.values,
                    line=dict(color="#34d399", width=2),
                    fill="tozeroy", fillcolor="rgba(52,211,153,0.08)",
                    mode="lines+markers", marker=dict(size=6),
                    name="Renewable share",
                ))
                fig_mre.update_layout(
                    title=f"Monthly Renewable Generation Share — {country_label} (%)",
                    template="plotly_dark", showlegend=False,
                    margin=dict(l=0, r=0, t=40, b=0), height=CH_SM,
                    yaxis=dict(title="%", range=[0, 105]),
                )
                _add_crisis_line(fig_mre, monthly_re.index)
                st.plotly_chart(fig_mre, width='stretch')
            else:
                re = renewable_share(gen)
                st.metric("Renewable share (period)", f"{re}%")

        # ── CPI in context ─────────────────────────────────────────────────────
        if inflation is not None:
            st.markdown('<div class="section-title">🏷️ Inflation in Context</div>', unsafe_allow_html=True)
            st.caption("General CPI and energy CPI over the selected period. Energy CPI typically lags electricity market movements by 1–3 months.")

            cpi_s    = inflation["cpi"]
            energy_s = inflation["energy"]

            # Eurostat HICP has a ~2 month publication lag — the most recent
            # available data point is typically 6-10 weeks behind "today".
            # Filter to a window around the selected range, but if that window
            # has no data (common for recent ranges), fall back to the last
            # 12 months of available data.
            period_start = pd.Period(start_date, freq="M")
            period_end   = pd.Period(end_date,   freq="M")
            cpi_filtered    = cpi_s[   (cpi_s.index    >= period_start) & (cpi_s.index    <= period_end)]
            energy_filtered = energy_s[(energy_s.index >= period_start) & (energy_s.index <= period_end)]

            used_fallback = False
            if len(cpi_filtered) == 0:
                # Fall back to last 12 months of available data
                cpi_filtered    = cpi_s.iloc[-12:]
                energy_filtered = energy_s.reindex(cpi_filtered.index)
                used_fallback   = True

            if len(cpi_filtered) > 0:
                if used_fallback:
                    st.info(
                        f"ℹ️ The selected date range ({start_date} → {end_date}) is more recent than Eurostat's "
                        f"latest HICP release. Showing the last 12 months of available inflation data "
                        f"({cpi_filtered.index[0]} → {cpi_filtered.index[-1]}) instead."
                    )

                fig_cpi = go.Figure()
                fig_cpi.add_trace(go.Scatter(
                    x=cpi_filtered.index.to_timestamp(), y=cpi_filtered.values,
                    name="General CPI", line=dict(color="#6366f1", width=2),
                    mode="lines+markers",
                ))
                fig_cpi.add_trace(go.Scatter(
                    x=energy_filtered.index.to_timestamp(), y=energy_filtered.values,
                    name="Energy & Housing CPI", line=dict(color="#f59e0b", width=2, dash="dot"),
                    mode="lines+markers",
                ))
                fig_cpi.add_hline(y=2, line_dash="dot", line_color="#374151", line_width=1,
                                  annotation_text="ECB 2%", annotation_position="bottom right")
                fig_cpi.add_hline(y=0, line_dash="dash", line_color="#374151", line_width=1)
                fig_cpi.update_layout(
                    title=f"Inflation — {country_label} (% YoY)",
                    template="plotly_dark",
                    margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                    yaxis_title="% YoY",
                    legend=dict(orientation="h", y=-0.18),
                )
                _add_crisis_line(fig_cpi, cpi_filtered.index.to_timestamp())
                st.plotly_chart(fig_cpi, width='stretch')
            else:
                st.info("No inflation data available. The long-term view in Tab 1 shows the full history.")


        # ── CSV Downloads ──────────────────────────────────────────────────────
        st.divider()
        st.markdown('<div class="section-title">⬇️ Download Data</div>', unsafe_allow_html=True)
        dl1, dl2, dl3 = st.columns(3)
        if prices is not None and len(prices) > 0:
            csv_prices = monthly_avg_prices(prices).reset_index()
            csv_prices.columns = ["Month", "Avg_Price_EUR_MWh"]
            dl1.download_button(
                "📥 Monthly Prices (CSV)",
                csv_prices.to_csv(index=False),
                file_name=f"{country_code}_monthly_prices.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t2_prices",
            )
        if gen is not None and len(gen) > 0:
            csv_gen = monthly_renewable_share(gen).reset_index()
            csv_gen.columns = ["Month", "Renewable_Share_Pct"]
            dl2.download_button(
                "📥 Monthly Renewable Share (CSV)",
                csv_gen.to_csv(index=False),
                file_name=f"{country_code}_renewable_share.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t2_renewable",
            )
        if inflation is not None:
            csv_inf = pd.DataFrame({
                "Month": [str(p) for p in inflation["cpi"].index],
                "General_CPI_YoY_Pct": inflation["cpi"].values,
                "Energy_CPI_YoY_Pct":  inflation["energy"].reindex(inflation["cpi"].index).values,
            })
            dl3.download_button(
                "📥 Inflation (CSV)",
                csv_inf.to_csv(index=False),
                file_name=f"{country_code}_inflation.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t2_inflation",
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — OPERATIONAL VIEW  (Short-term, days/weeks)
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    _b = _stale_banner(
        st.session_state.get("fetched_country"), country_code,
        country_label, st.session_state.get("fetched_country_label"),
        st.session_state.get("fetched_start"), st.session_state.get("fetched_end"),
        str(start_date), str(end_date),
    )
    if _b: st.markdown(_b, unsafe_allow_html=True)
    st.markdown(f"### ⚡ Operational View — {country_label}")
    st.markdown("""
    <div class="thesis-box">
    <strong>What this tab shows:</strong> Day-to-day electricity market conditions —
    hourly prices, generation mix, and cheapest/most expensive hours.
    Note: short-term generation reflects weather and demand, not structural investment.
    Use Tab 1 for the structural picture.
    </div>
    """, unsafe_allow_html=True)

    if prices is None and gen is None:
        if fetch_attempted:
            st.warning("Operational data could not be loaded — ENTSO-E may be temporarily unavailable (503). Try again shortly.")
        else:
            st.info("Click **Fetch Data** to load operational data.")
    else:
        # ── Price summary metrics ──────────────────────────────────────────────
        if prices is not None and len(prices) > 0:
            st.markdown('<div class="section-title">💶 Day-Ahead Price Summary</div>', unsafe_allow_html=True)

            stats = price_summary(prices)
            vol   = price_volatility(prices)

            # Row 1: avg, median, volatility
            r1c1, r1c2, r1c3 = st.columns(3)
            r1c1.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Average</div>
                <div class="metric-value">{stats["mean"]}</div>
                <div class="metric-unit">€/MWh</div>
            </div>""", unsafe_allow_html=True)
            r1c2.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Median</div>
                <div class="metric-value">{stats["median"]}</div>
                <div class="metric-unit">€/MWh</div>
            </div>""", unsafe_allow_html=True)
            r1c3.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Volatility (σ)</div>
                <div class="metric-value">{vol}</div>
                <div class="metric-unit">€/MWh · lower = stable</div>
            </div>""", unsafe_allow_html=True)

            # Row 2: min, max
            r2c1, r2c2, _ = st.columns(3)
            r2c1.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Min</div>
                <div class="metric-value">{stats["min"]}</div>
                <div class="metric-unit">€/MWh</div>
            </div>""", unsafe_allow_html=True)
            r2c2.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Max</div>
                <div class="metric-value">{stats["max"]}</div>
                <div class="metric-unit">€/MWh</div>
            </div>""", unsafe_allow_html=True)

            st.markdown("")

            # Hourly price chart
            fig_prices = px.line(
                prices,
                title=f"Hourly Day-Ahead Prices — {country_label}",
                labels={"value": "€/MWh", "index": ""},
                color_discrete_sequence=["#6366f1"],
            )
            fig_prices.update_layout(
                template="plotly_dark", showlegend=False,
                margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
            )
            _add_crisis_line(fig_prices, prices.index)
            st.plotly_chart(fig_prices, width='stretch')
            ts_start_dt = pd.Timestamp(start_date)
            ts_end_dt   = pd.Timestamp(end_date) + pd.Timedelta(days=1)
            st.markdown(_last_updated("fetch_day_ahead_prices", country_code, ts_start_dt, ts_end_dt), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="section-title">🟢 5 Cheapest Hours</div>', unsafe_allow_html=True)
                cheap = cheapest_hours(prices, 5).reset_index()
                cheap.columns = ["Datetime", "€/MWh"]
                cheap["Datetime"] = cheap["Datetime"].dt.strftime("%a %d %b  %H:%M")
                st.dataframe(cheap, hide_index=True, width='stretch')
            with c2:
                st.markdown('<div class="section-title">🔴 5 Most Expensive Hours</div>', unsafe_allow_html=True)
                exp = most_expensive_hours(prices, 5).reset_index()
                exp.columns = ["Datetime", "€/MWh"]
                exp["Datetime"] = exp["Datetime"].dt.strftime("%a %d %b  %H:%M")
                st.dataframe(exp, hide_index=True, width='stretch')

        # ── Generation mix ─────────────────────────────────────────────────────
        if gen is not None and len(gen) > 0:
            st.markdown('<div class="section-title">🏭 Generation Mix</div>', unsafe_allow_html=True)

            re_share  = renewable_share(gen)
            total_gwh = round(gen.sum().sum() / 1000, 0)

            m1, m2 = st.columns(2)
            m1.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Renewable Share</div>
                <div class="metric-value">{re_share}%</div>
                <div class="metric-unit">of total generation · selected period</div>
            </div>""", unsafe_allow_html=True)
            m2.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Total Generation</div>
                <div class="metric-value">{total_gwh:,.0f}</div>
                <div class="metric-unit">GWh in period</div>
            </div>""", unsafe_allow_html=True)

            st.markdown("")
            st.caption("⚠️ Generation mix over short periods reflects weather conditions, not structural investment. See Tab 1 for the installed capacity picture.")

            g1, g2 = st.columns([3, 2])
            with g1:
                daily_gen    = daily_avg_generation(gen)
                re_cols      = [c for c in daily_gen.columns if c in RENEWABLE_SOURCES]
                nu_cols      = [c for c in daily_gen.columns if c in NUCLEAR_SOURCES]
                fo_cols      = [c for c in daily_gen.columns if c in FOSSIL_SOURCES]
                ot_cols      = [c for c in daily_gen.columns
                                if c not in RENEWABLE_SOURCES
                                and c not in NUCLEAR_SOURCES
                                and c not in FOSSIL_SOURCES]
                ordered_cols = re_cols + nu_cols + fo_cols + ot_cols
                color_map    = {c: tier_color(c) for c in ordered_cols}

                fig_area = px.area(
                    daily_gen[ordered_cols],
                    title="Daily Average Generation by Source (MW)",
                    labels={"value": "MW", "index": "", "variable": "Source"},
                    color_discrete_map=color_map,
                )
                fig_area.update_layout(
                    template="plotly_dark",
                    margin=dict(l=0, r=0, t=40, b=0), height=CH_LG,
                    legend=dict(orientation="h", y=-0.25),
                )
                st.plotly_chart(fig_area, width='stretch')

            with g2:
                mix = generation_mix_pct(gen)
                colors_pie = [tier_color(s) for s in mix.index]
                fig_pie = go.Figure(go.Pie(
                    values=mix.values, labels=mix.index,
                    hole=0.4, marker=dict(colors=colors_pie),
                    textinfo="label+percent",
                ))
                fig_pie.update_layout(
                    title="Generation Mix (%)",
                    template="plotly_dark",
                    margin=dict(l=0, r=0, t=40, b=0), height=CH_LG,
                    showlegend=False,
                )
                st.plotly_chart(fig_pie, width='stretch')

            # Total by source bar chart
            totals  = total_by_source(gen)
            colors  = [tier_color(s) for s in totals.index]
            fig_bar = go.Figure(go.Bar(
                x=totals.index, y=totals.values,
                marker_color=colors,
                text=totals.values.astype(int), textposition="outside",
            ))
            fig_bar.update_layout(
                title="Total Generation per Source (MWh)",
                template="plotly_dark", showlegend=False,
                margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                yaxis_title="MWh",
            )
            st.plotly_chart(fig_bar, width='stretch')

        # ── CSV Downloads ──────────────────────────────────────────────────────
        if prices is not None or gen is not None:
            st.divider()
            st.markdown('<div class="section-title">⬇️ Download Data</div>', unsafe_allow_html=True)
            dl1, dl2 = st.columns(2)
            if prices is not None and len(prices) > 0:
                csv_hourly = prices.reset_index()
                csv_hourly.columns = ["Datetime", "Price_EUR_MWh"]
                dl1.download_button(
                    "📥 Hourly Prices (CSV)",
                    csv_hourly.to_csv(index=False),
                    file_name=f"{country_code}_hourly_prices.csv",
                    mime="text/csv",
                    width='stretch',
                    key="dl_t3_prices",
                )
            if gen is not None and len(gen) > 0:
                csv_gen_daily = daily_avg_generation(gen).reset_index()
                dl2.download_button(
                    "📥 Daily Generation Mix (CSV)",
                    csv_gen_daily.to_csv(index=False),
                    file_name=f"{country_code}_generation_mix.csv",
                    mime="text/csv",
                    width='stretch',
                    key="dl_t3_generation",
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — COUNTRY COMPARISON
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    if not compare_enabled:
        st.markdown("## 🔀 Country Comparison")
        st.info("Enable **Compare with** in the sidebar and click **Fetch Data** to compare two countries.")
    elif all(v is None for v in [cmp_prices, cmp_gen, cmp_inflation, cmp_capacity]):
        st.info("Click **Fetch Data** to load comparison data.")
    else:
        # Stale banners for primary and compare country independently
        _b1 = _stale_banner(
            st.session_state.get("fetched_country"), country_code,
            country_label, st.session_state.get("fetched_country_label"),
            st.session_state.get("fetched_start"), st.session_state.get("fetched_end"),
            str(start_date), str(end_date),
        )
        _b2 = _stale_banner(
            st.session_state.get("fetched_cmp_country"),
            compare_code if compare_enabled else None,
            compare_label if compare_label else "",
            st.session_state.get("fetched_cmp_label"),
        )
        if _b1: st.markdown(_b1, unsafe_allow_html=True)
        if _b2: st.markdown(_b2, unsafe_allow_html=True)
        st.markdown(f"### 🔀 {country_label}  vs  {compare_label}")
        st.markdown("""
        <div class="thesis-box">
        <strong>What this tab shows:</strong> The full causal chain side by side —
        from renewable capacity investment, through import dependency, to electricity prices and inflation.
        Countries that invested more in renewables should show lower and more stable energy CPI over time.
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f"""
        <div style='display:flex; gap:1.2rem; flex-wrap:wrap; align-items:center; margin:0.4rem 0 0.6rem; font-size:0.78rem; color:#9ca3af; font-family:DM Mono, monospace;'>
            <strong style='color:#6366f1'>Energy classification:</strong>
            <span><span style='display:inline-block; width:12px; height:12px; background:{TIER_COLORS["renewable"]}; border-radius:3px; vertical-align:middle; margin-right:6px;'></span>Renewable (zero fuel imports)</span>
            <span><span style='display:inline-block; width:12px; height:12px; background:{TIER_COLORS["nuclear"]}; border-radius:3px; vertical-align:middle; margin-right:6px;'></span>Nuclear (uranium imported, low price exposure)</span>
            <span><span style='display:inline-block; width:12px; height:12px; background:{TIER_COLORS["fossil"]}; border-radius:3px; vertical-align:middle; margin-right:6px;'></span>Fossil (gas / coal / oil — high import dependency)</span>
        </div>
        """, unsafe_allow_html=True)
        # ── Data status strip ──────────────────────────────────────────────────
        def _status(val, label):
            ok = val is not None and (not hasattr(val, "__len__") or len(val) > 0)
            icon = "🟢" if ok else "🔴"
            return f"{icon} {label}"

        st.markdown(
            f"<div style='font-size:0.72rem; color:#6b7280; font-family:DM Mono,monospace; "
            f"margin-bottom:0.6rem; line-height:2;'>"
            f"📅 <strong>{start_date} → {end_date}</strong> &nbsp;·&nbsp; "
            f"{_status(prices, f'{country_label} prices')} &nbsp;"
            f"{_status(cmp_prices, f'{compare_label} prices')} &nbsp;"
            f"{_status(gen, f'{country_label} gen')} &nbsp;"
            f"{_status(cmp_gen, f'{compare_label} gen')} &nbsp;"
            f"{_status(inflation, f'{country_label} CPI')} &nbsp;"
            f"{_status(cmp_inflation, f'{compare_label} CPI')} &nbsp;"
            f"{_status(import_dep, f'{country_label} imports')} &nbsp;"
            f"{_status(cmp_import_dep, f'{compare_label} imports')}"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── Score summary ──────────────────────────────────────────────────────
        # Compute wins/losses across all available metrics before rendering anything
        _scores = {country_label: 0, compare_label: 0}
        _total  = 0

        def _get_cap_share(cap_df):
            if cap_df is None or cap_df.empty:
                return None
            re_cols = [c for c in cap_df.columns if c in RENEWABLE_SOURCES]
            if not re_cols:
                return None
            tot = cap_df.sum(axis=1)
            re  = cap_df[re_cols].sum(axis=1)
            s   = (re / tot * 100).round(1)
            return s.iloc[-1] if len(s) > 0 else None

        _metrics = []

        cap_a_score = _get_cap_share(capacity)
        cap_b_score = _get_cap_share(cmp_capacity)
        if cap_a_score is not None and cap_b_score is not None:
            _total += 1
            if cap_a_score > cap_b_score:
                _scores[country_label] += 1
                _metrics.append(("🔋 Renewable Capacity", country_label, f"{cap_a_score:.1f}% vs {cap_b_score:.1f}%"))
            elif cap_b_score > cap_a_score:
                _scores[compare_label] += 1
                _metrics.append(("🔋 Renewable Capacity", compare_label, f"{cap_b_score:.1f}% vs {cap_a_score:.1f}%"))

        re_a_score = renewable_share(gen)     if gen     is not None else None
        re_b_score = renewable_share(cmp_gen) if cmp_gen is not None else None
        if re_a_score is not None and re_b_score is not None:
            _total += 1
            if re_a_score > re_b_score:
                _scores[country_label] += 1
                _metrics.append(("🌱 Generation Share", country_label, f"{re_a_score}% vs {re_b_score}%"))
            elif re_b_score > re_a_score:
                _scores[compare_label] += 1
                _metrics.append(("🌱 Generation Share", compare_label, f"{re_b_score}% vs {re_a_score}%"))

        vol_a_score = price_volatility(prices)     if prices     is not None else None
        vol_b_score = price_volatility(cmp_prices) if cmp_prices is not None else None
        if vol_a_score is not None and vol_b_score is not None:
            _total += 1
            if vol_a_score < vol_b_score:
                _scores[country_label] += 1
                _metrics.append(("📉 Price Volatility", country_label, f"{vol_a_score} vs {vol_b_score} €/MWh σ"))
            elif vol_b_score < vol_a_score:
                _scores[compare_label] += 1
                _metrics.append(("📉 Price Volatility", compare_label, f"{vol_b_score} vs {vol_a_score} €/MWh σ"))

        if inflation is not None and cmp_inflation is not None:
            _total += 2
            if inflation["latest_cpi"] < cmp_inflation["latest_cpi"]:
                _scores[country_label] += 1
                _metrics.append(("🏷️ General CPI", country_label,
                    f"{inflation['latest_cpi']:+.1f}% vs {cmp_inflation['latest_cpi']:+.1f}%"))
            else:
                _scores[compare_label] += 1
                _metrics.append(("🏷️ General CPI", compare_label,
                    f"{cmp_inflation['latest_cpi']:+.1f}% vs {inflation['latest_cpi']:+.1f}%"))
            if inflation["latest_energy"] < cmp_inflation["latest_energy"]:
                _scores[country_label] += 1
                _metrics.append(("⚡ Energy CPI", country_label,
                    f"{inflation['latest_energy']:+.1f}% vs {cmp_inflation['latest_energy']:+.1f}%"))
            else:
                _scores[compare_label] += 1
                _metrics.append(("⚡ Energy CPI", compare_label,
                    f"{cmp_inflation['latest_energy']:+.1f}% vs {inflation['latest_energy']:+.1f}%"))

        if import_dep is not None and cmp_import_dep is not None and len(import_dep) > 0 and len(cmp_import_dep) > 0:
            _total += 1
            if import_dep.iloc[-1] < cmp_import_dep.iloc[-1]:
                _scores[country_label] += 1
                _metrics.append(("🛢️ Import Dependency", country_label,
                    f"{import_dep.iloc[-1]:.1f}% vs {cmp_import_dep.iloc[-1]:.1f}%"))
            elif cmp_import_dep.iloc[-1] < import_dep.iloc[-1]:
                _scores[compare_label] += 1
                _metrics.append(("🛢️ Import Dependency", compare_label,
                    f"{cmp_import_dep.iloc[-1]:.1f}% vs {import_dep.iloc[-1]:.1f}%"))

        if household_price is not None and cmp_household_price is not None and len(household_price) > 0 and len(cmp_household_price) > 0:
            _total += 1
            if household_price.iloc[-1] < cmp_household_price.iloc[-1]:
                _scores[country_label] += 1
                _metrics.append(("🔌 Household Price", country_label,
                    f"{household_price.iloc[-1]:.4f} vs {cmp_household_price.iloc[-1]:.4f} €/kWh"))
            elif cmp_household_price.iloc[-1] < household_price.iloc[-1]:
                _scores[compare_label] += 1
                _metrics.append(("🔌 Household Price", compare_label,
                    f"{cmp_household_price.iloc[-1]:.4f} vs {household_price.iloc[-1]:.4f} €/kWh"))

        # Render the scoreboard
        if _total > 0:
            sc_a = _scores[country_label]
            sc_b = _scores[compare_label]
            overall_winner = country_label if sc_a > sc_b else (compare_label if sc_b > sc_a else None)

            sb1, sb2, sb3 = st.columns(3)
            sb1.markdown(cmp_card(
                country_label, f"{sc_a} / {_total}", "metrics won",
                "win" if sc_a > sc_b else ("loss" if sc_a < sc_b else "neutral")
            ), unsafe_allow_html=True)
            sb2.markdown(cmp_card(
                compare_label, f"{sc_b} / {_total}", "metrics won",
                "win" if sc_b > sc_a else ("loss" if sc_b < sc_a else "neutral")
            ), unsafe_allow_html=True)
            if overall_winner:
                sb3.markdown(cmp_card(
                    "Overall Leader", overall_winner, "wins more metrics",
                    result="overall",
                ), unsafe_allow_html=True)
            else:
                sb3.markdown(cmp_card("Overall", "Tied", f"{sc_a}–{sc_b}"), unsafe_allow_html=True)

            with st.expander("📋 Metric breakdown"):
                for metric, winner, detail in _metrics:
                    st.markdown(
                        f"**{metric}** → 🟢 {winner} &nbsp;&nbsp; <span style='color:#6b7280;font-size:0.85rem'>{detail}</span>",
                        unsafe_allow_html=True,
                    )

            # ── #8 Auto-generated causal narrative ────────────────────────────
            st.markdown('<div class="section-title">📝 Causal Chain Assessment</div>', unsafe_allow_html=True)

            _lines = []

            # Renewable capacity
            if cap_a_score is not None and cap_b_score is not None:
                cap_diff = round(abs(cap_a_score - cap_b_score), 1)
                cap_leader = country_label if cap_a_score > cap_b_score else compare_label
                cap_lagger = compare_label if cap_a_score > cap_b_score else country_label
                _lines.append(
                    f"**{cap_leader}** has {cap_diff}pp more renewable installed capacity "
                    f"({max(cap_a_score, cap_b_score):.1f}% vs {min(cap_a_score, cap_b_score):.1f}%), "
                    f"indicating stronger structural investment in renewables."
                )

            # Import dependency
            if import_dep is not None and cmp_import_dep is not None and len(import_dep) > 0 and len(cmp_import_dep) > 0:
                id_a = import_dep.iloc[-1]
                id_b = cmp_import_dep.iloc[-1]
                id_diff = round(abs(id_a - id_b), 1)
                id_leader = country_label if id_a < id_b else compare_label
                # Trend
                trend_a = round(import_dep.iloc[-1] - import_dep.iloc[0], 1) if len(import_dep) > 1 else 0
                trend_b = round(cmp_import_dep.iloc[-1] - cmp_import_dep.iloc[0], 1) if len(cmp_import_dep) > 1 else 0
                trend_str_a = f"{'↓' if trend_a < 0 else '↑'} {abs(trend_a):.1f}pp"
                trend_str_b = f"{'↓' if trend_b < 0 else '↑'} {abs(trend_b):.1f}pp"
                _lines.append(
                    f"On energy import dependency, **{id_leader}** is {id_diff}pp less dependent on imports "
                    f"({min(id_a, id_b):.1f}% vs {max(id_a, id_b):.1f}%). "
                    f"Over the selected period, {country_label} trended {trend_str_a} and {compare_label} trended {trend_str_b}."
                )

            # Price volatility
            if vol_a_score is not None and vol_b_score is not None:
                vol_diff = round(abs(vol_a_score - vol_b_score), 2)
                vol_leader = country_label if vol_a_score < vol_b_score else compare_label
                _lines.append(
                    f"**{vol_leader}** shows lower electricity price volatility "
                    f"({min(vol_a_score, vol_b_score)} vs {max(vol_a_score, vol_b_score)} €/MWh std dev), "
                    f"suggesting a more stable energy market."
                )

            # CPI
            if inflation is not None and cmp_inflation is not None:
                ecpi_a = inflation["latest_energy"]
                ecpi_b = cmp_inflation["latest_energy"]
                ecpi_diff = round(abs(ecpi_a - ecpi_b), 1)
                ecpi_leader = country_label if ecpi_a < ecpi_b else compare_label
                _lines.append(
                    f"On energy CPI, **{ecpi_leader}** has {ecpi_diff}pp lower energy inflation "
                    f"({min(ecpi_a, ecpi_b):+.1f}% vs {max(ecpi_a, ecpi_b):+.1f}% YoY)."
                )

            # Thesis consistency check
            if cap_a_score is not None and cap_b_score is not None and import_dep is not None and cmp_import_dep is not None and len(import_dep) > 0 and len(cmp_import_dep) > 0 and inflation is not None and cmp_inflation is not None:
                cap_leader  = country_label if cap_a_score > cap_b_score else compare_label
                id_leader   = country_label if import_dep.iloc[-1] < cmp_import_dep.iloc[-1] else compare_label
                ecpi_leader = country_label if inflation["latest_energy"] < cmp_inflation["latest_energy"] else compare_label
                consistent  = (cap_leader == id_leader == ecpi_leader)
                if consistent:
                    _lines.append(
                        f"✅ **These results are consistent with the causal thesis**: "
                        f"**{cap_leader}** leads on renewable capacity, has lower import dependency, "
                        f"and lower energy CPI — all three links in the chain point the same direction."
                    )
                else:
                    _lines.append(
                        f"⚠️ **Mixed results**: The causal chain does not hold cleanly for this comparison. "
                        f"Renewable capacity leader: **{cap_leader}** · "
                        f"Import dependency leader: **{id_leader}** · "
                        f"Energy CPI leader: **{ecpi_leader}**. "
                        f"This may reflect market design differences, gas price exposure, or data lag."
                    )

            for line in _lines:
                st.markdown(line)
                st.markdown("")

        st.divider()

        # ── Renewable capacity share comparison ────────────────────────────────
        st.markdown('<div class="section-title">🔋 Installed Renewable Capacity Share</div>', unsafe_allow_html=True)

        def get_latest_cap_share(cap_df):
            if cap_df is None or cap_df.empty:
                return None
            re_cols = [c for c in cap_df.columns if c in RENEWABLE_SOURCES]
            if not re_cols:
                return None
            total = cap_df.sum(axis=1)
            re    = cap_df[re_cols].sum(axis=1)
            share = (re / total * 100).round(1)
            return share.iloc[-1] if len(share) > 0 else None

        cap_a = get_latest_cap_share(capacity)
        cap_b = get_latest_cap_share(cmp_capacity)

        if cap_a is not None or cap_b is not None:
            r1, r2, r3 = st.columns(3)
            if cap_a is not None:
                win_a = cap_a > cap_b if cap_b is not None else False
                r1.markdown(cmp_card(
                    country_label, f"{cap_a:.1f}%", "renewable installed capacity",
                    "win" if win_a else ("loss" if cap_b is not None else "neutral")
                ), unsafe_allow_html=True)
            if cap_b is not None:
                win_b = cap_b > cap_a if cap_a is not None else False
                r2.markdown(cmp_card(
                    compare_label, f"{cap_b:.1f}%", "renewable installed capacity",
                    "win" if win_b else ("loss" if cap_a is not None else "neutral")
                ), unsafe_allow_html=True)
            if cap_a is not None and cap_b is not None:
                diff = round(cap_a - cap_b, 1)
                leader = country_label if diff > 0 else compare_label
                r3.markdown(cmp_card("Difference", f"{abs(diff):.1f}pp", f"{leader} leads"), unsafe_allow_html=True)
        else:
            st.info("Installed capacity data unavailable for one or both countries.")

        # ── Renewable generation share comparison ──────────────────────────────
        st.markdown('<div class="section-title">🌱 Renewable Generation Share (selected period)</div>', unsafe_allow_html=True)
        st.caption("Short-term generation reflects weather. For structural comparison, see installed capacity above.")

        re_a = renewable_share(gen)     if gen     is not None else None
        re_b = renewable_share(cmp_gen) if cmp_gen is not None else None

        g1, g2, g3 = st.columns(3)
        if re_a is not None:
            g1.markdown(cmp_card(
                country_label, f"{re_a}%", "generation share",
                "win" if (re_b is not None and re_a > re_b) else ("loss" if re_b is not None else "neutral")
            ), unsafe_allow_html=True)
        if re_b is not None:
            g2.markdown(cmp_card(
                compare_label, f"{re_b}%", "generation share",
                "win" if (re_a is not None and re_b > re_a) else ("loss" if re_a is not None else "neutral")
            ), unsafe_allow_html=True)
        if re_a is not None and re_b is not None:
            diff_re = round(re_a - re_b, 1)
            leader  = country_label if diff_re > 0 else compare_label
            g3.markdown(cmp_card("Difference", f"{abs(diff_re)}pp", f"{leader} leads"), unsafe_allow_html=True)

        # ── Nuclear share comparison ──────────────────────────────────────────
        st.markdown('<div class="section-title">⚛️ Nuclear Generation Share (selected period)</div>', unsafe_allow_html=True)
        st.caption(
            "Nuclear is low-carbon but NOT renewable — uranium is imported (typically from Kazakhstan, "
            "Niger, Canada, Australia). It reduces fuel-price exposure but does not eliminate import dependency."
        )

        nu_a = nuclear_share(gen)     if gen     is not None else None
        nu_b = nuclear_share(cmp_gen) if cmp_gen is not None else None

        n1, n2, n3 = st.columns(3)
        if nu_a is not None:
            # Note: for nuclear share we don't apply win/loss logic — it's neither
            # clearly "good" nor "bad" depending on the user's perspective.
            n1.markdown(cmp_card(country_label, f"{nu_a}%", "nuclear share"), unsafe_allow_html=True)
        if nu_b is not None:
            n2.markdown(cmp_card(compare_label, f"{nu_b}%", "nuclear share"), unsafe_allow_html=True)
        if nu_a is not None and nu_b is not None:
            # Combined low-carbon share (renewable + nuclear) is the climate-relevant total
            lc_a = round(nu_a + (re_a or 0), 1)
            lc_b = round(nu_b + (re_b or 0), 1)
            lc_leader = country_label if lc_a > lc_b else compare_label
            n3.markdown(cmp_card(
                "Combined Low-Carbon", f"{max(lc_a, lc_b)}% vs {min(lc_a, lc_b)}%",
                f"{lc_leader} leads (renewable + nuclear)"
            ), unsafe_allow_html=True)

        # ── Price volatility comparison ─────────────────────────────────────────
        st.markdown('<div class="section-title">📉 Price Volatility</div>', unsafe_allow_html=True)
        st.caption("Lower volatility = more stable energy market. Countries with high renewable share tend to have lower volatility over time.")

        vol_a = price_volatility(prices)     if prices     is not None else None
        vol_b = price_volatility(cmp_prices) if cmp_prices is not None else None

        v1, v2, v3 = st.columns(3)
        if vol_a is not None:
            v1.markdown(cmp_card(
                f"{country_label} — Volatility", str(vol_a), "€/MWh std dev",
                "win" if (vol_b is not None and vol_a < vol_b) else ("loss" if vol_b is not None else "neutral")
            ), unsafe_allow_html=True)
        if vol_b is not None:
            v2.markdown(cmp_card(
                f"{compare_label} — Volatility", str(vol_b), "€/MWh std dev",
                "win" if (vol_a is not None and vol_b < vol_a) else ("loss" if vol_a is not None else "neutral")
            ), unsafe_allow_html=True)
        if vol_a is not None and vol_b is not None:
            more_stable = country_label if vol_a < vol_b else compare_label
            v3.markdown(cmp_card("More Stable", more_stable, "lower price std dev", result="overall"), unsafe_allow_html=True)

        # Grouped price bar chart
        if prices is not None and cmp_prices is not None:
            avg_a = round(prices.mean(), 2)
            avg_b = round(cmp_prices.mean(), 2)
            fig_pb = go.Figure(go.Bar(
                x=[country_label, compare_label],
                y=[avg_a, avg_b],
                marker_color=["#6366f1", "#f59e0b"],
                text=[f"€{avg_a}", f"€{avg_b}"],
                textposition="outside",
            ))
            fig_pb.update_layout(
                title="Average Day-Ahead Price (€/MWh)",
                template="plotly_dark", showlegend=False,
                margin=dict(l=0, r=0, t=40, b=0), height=CH_SM,
                yaxis=dict(title="€/MWh"),
            )
            st.plotly_chart(fig_pb, width='stretch')

        # ── Inflation comparison ────────────────────────────────────────────────
        st.markdown('<div class="section-title">🏷️ Inflation Comparison</div>', unsafe_allow_html=True)

        if inflation is None or cmp_inflation is None:
            st.info("Inflation data missing for one or both countries.")
        else:
            cpi_a_val  = inflation['latest_cpi']
            cpi_b_val  = cmp_inflation['latest_cpi']
            enrg_a_val = inflation['latest_energy']
            enrg_b_val = cmp_inflation['latest_energy']

            # Row 1: General CPI
            inf1, inf2 = st.columns(2)
            inf1.markdown(cmp_card(
                f"{country_label} — General CPI", f"{cpi_a_val:+.1f}%", "latest YoY",
                "win" if cpi_a_val < cpi_b_val else "loss"
            ), unsafe_allow_html=True)
            inf2.markdown(cmp_card(
                f"{compare_label} — General CPI", f"{cpi_b_val:+.1f}%", "latest YoY",
                "win" if cpi_b_val < cpi_a_val else "loss"
            ), unsafe_allow_html=True)
            st.markdown("")
            # Row 2: Energy CPI
            inf3, inf4 = st.columns(2)
            inf3.markdown(cmp_card(
                f"{country_label} — Energy CPI", f"{enrg_a_val:+.1f}%", "latest YoY",
                "win" if enrg_a_val < enrg_b_val else "loss"
            ), unsafe_allow_html=True)
            inf4.markdown(cmp_card(
                f"{compare_label} — Energy CPI", f"{enrg_b_val:+.1f}%", "latest YoY",
                "win" if enrg_b_val < enrg_a_val else "loss"
            ), unsafe_allow_html=True)

            st.markdown("")

            cpi_a  = inflation["cpi"]
            cpi_b  = cmp_inflation["cpi"]
            enrg_a = inflation["energy"]
            enrg_b = cmp_inflation["energy"]

            fig_cpi = go.Figure()
            fig_cpi.add_trace(go.Scatter(
                x=cpi_a.index.to_timestamp(), y=cpi_a.values,
                name=f"{country_label} — General CPI",
                line=dict(color="#6366f1", width=2),
            ))
            fig_cpi.add_trace(go.Scatter(
                x=cpi_b.index.to_timestamp(), y=cpi_b.values,
                name=f"{compare_label} — General CPI",
                line=dict(color="#f59e0b", width=2),
            ))
            fig_cpi.add_hline(y=2, line_dash="dot", line_color="#374151", line_width=1,
                              annotation_text="ECB 2% target", annotation_position="bottom right")
            fig_cpi.update_layout(
                title="General CPI Comparison (% YoY)",
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                yaxis_title="% YoY",
                legend=dict(orientation="h", y=-0.18),
            )
            _add_crisis_line(fig_cpi, cpi_a.index.to_timestamp())
            st.plotly_chart(fig_cpi, width='stretch')

            fig_ecpi = go.Figure()
            fig_ecpi.add_trace(go.Scatter(
                x=enrg_a.index.to_timestamp(), y=enrg_a.values,
                name=f"{country_label} — Energy CPI",
                line=dict(color="#6366f1", width=2, dash="dot"),
            ))
            fig_ecpi.add_trace(go.Scatter(
                x=enrg_b.index.to_timestamp(), y=enrg_b.values,
                name=f"{compare_label} — Energy CPI",
                line=dict(color="#f59e0b", width=2, dash="dot"),
            ))
            fig_ecpi.add_hline(y=0, line_dash="dash", line_color="#374151", line_width=1)
            fig_ecpi.update_layout(
                title="Energy & Housing CPI Comparison (% YoY)",
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                yaxis_title="% YoY",
                legend=dict(orientation="h", y=-0.18),
            )
            _add_crisis_line(fig_ecpi, enrg_a.index.to_timestamp())
            st.plotly_chart(fig_ecpi, width='stretch')

        # ── Generation mix side by side ────────────────────────────────────────
        st.markdown('<div class="section-title">🏭 Generation Mix (selected period)</div>', unsafe_allow_html=True)

        pie_a, pie_b = st.columns(2)

        def render_mix_pie(container, gen_df, label):
            with container:
                if gen_df is not None and len(gen_df) > 0:
                    mix    = generation_mix_pct(gen_df)
                    colors = [tier_color(s) for s in mix.index]
                    fig    = go.Figure(go.Pie(
                        labels=mix.index, values=mix.values,
                        hole=0.42, marker=dict(colors=colors),
                        textinfo="label+percent",
                    ))
                    fig.update_layout(
                        title=label, template="plotly_dark",
                        margin=dict(l=0, r=0, t=40, b=0), height=CH_LG,
                        showlegend=False,
                    )
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info(f"No generation data for {label}.")

        render_mix_pie(pie_a, gen,     country_label)
        render_mix_pie(pie_b, cmp_gen, compare_label)

        # ── Import dependency comparison ────────────────────────────────────────
        st.markdown('<div class="section-title">🛢️ Energy Import Dependency</div>', unsafe_allow_html=True)
        st.caption("The key causal link: higher renewable capacity → lower import dependency → less exposure to fossil fuel price shocks → lower energy CPI.")

        has_id_a = import_dep     is not None and len(import_dep)     > 0
        has_id_b = cmp_import_dep is not None and len(cmp_import_dep) > 0

        if has_id_a or has_id_b:
            # Latest value metric cards
            id1, id2, id3 = st.columns(3)
            if has_id_a:
                id1.markdown(cmp_card(
                    country_label, f"{import_dep.iloc[-1]:.1f}%",
                    f"import dependency · {import_dep.index[-1]}",
                    "win" if (has_id_b and import_dep.iloc[-1] < cmp_import_dep.iloc[-1]) else ("loss" if has_id_b else "neutral")
                ), unsafe_allow_html=True)
            if has_id_b:
                id2.markdown(cmp_card(
                    compare_label, f"{cmp_import_dep.iloc[-1]:.1f}%",
                    f"import dependency · {cmp_import_dep.index[-1]}",
                    "win" if (has_id_a and cmp_import_dep.iloc[-1] < import_dep.iloc[-1]) else ("loss" if has_id_a else "neutral")
                ), unsafe_allow_html=True)
            if has_id_a and has_id_b:
                diff_id = round(import_dep.iloc[-1] - cmp_import_dep.iloc[-1], 1)
                more_independent = compare_label if diff_id > 0 else country_label
                id3.markdown(cmp_card(
                    "More Energy-Independent", more_independent, f"by {abs(diff_id):.1f}pp",
                    result="overall",
                ), unsafe_allow_html=True)

            st.markdown("")

            # Overlapping line chart
            fig_id_cmp = go.Figure()
            if has_id_a:
                fig_id_cmp.add_trace(go.Scatter(
                    x=import_dep.index, y=import_dep.values,
                    name=country_label,
                    line=dict(color="#6366f1", width=2),
                    mode="lines+markers", marker=dict(size=5),
                    hovertemplate="%{x}<br>%{y:.1f}%<extra>" + country_label + "</extra>",
                ))
            if has_id_b:
                fig_id_cmp.add_trace(go.Scatter(
                    x=cmp_import_dep.index, y=cmp_import_dep.values,
                    name=compare_label,
                    line=dict(color="#f59e0b", width=2),
                    mode="lines+markers", marker=dict(size=5),
                    hovertemplate="%{x}<br>%{y:.1f}%<extra>" + compare_label + "</extra>",
                ))
            fig_id_cmp.add_hline(
                y=0, line_dash="dash", line_color="#374151", line_width=1,
                annotation_text="Net exporter threshold",
                annotation_position="bottom right",
            )
            fig_id_cmp.add_hline(
                y=55, line_dash="dot", line_color="#4b5563", line_width=1,
                annotation_text="~EU average (55%)",
                annotation_position="top right",
            )
            fig_id_cmp.update_layout(
                title="Energy Import Dependency Comparison (% of total energy)",
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                yaxis_title="%",
                xaxis_title="Year",
                legend=dict(orientation="h", y=-0.18),
            )
            _add_crisis_line(fig_id_cmp, import_dep.index)
            st.plotly_chart(fig_id_cmp, width='stretch')

            # Trend summary: is each country becoming more or less dependent?
            if has_id_a and has_id_b:
                trend_a = round(import_dep.iloc[-1]     - import_dep.iloc[0],     1)
                trend_b = round(cmp_import_dep.iloc[-1] - cmp_import_dep.iloc[0], 1)
                ta_sign = "+" if trend_a >= 0 else ""
                tb_sign = "+" if trend_b >= 0 else ""
                ta_dir  = "↑ more dependent" if trend_a > 0 else "↓ less dependent"
                tb_dir  = "↑ more dependent" if trend_b > 0 else "↓ less dependent"
                st.caption(
                    f"**Trend over period:** {country_label}: {ta_sign}{trend_a}pp ({ta_dir})  ·  "
                    f"{compare_label}: {tb_sign}{trend_b}pp ({tb_dir})"
                )
        else:
            st.info("Energy import dependency data unavailable for one or both countries.")

        # ── Household electricity price comparison ─────────────────────────────
        st.markdown('<div class="section-title">🔌 Household Electricity Prices</div>', unsafe_allow_html=True)
        st.caption("Consumer-facing price (excl. taxes) — more directly linked to household inflation than wholesale day-ahead prices.")

        has_hp_a = household_price     is not None and len(household_price)     > 0
        has_hp_b = cmp_household_price is not None and len(cmp_household_price) > 0

        if has_hp_a or has_hp_b:
            hp1, hp2, hp3 = st.columns(3)
            if has_hp_a:
                hp1.markdown(cmp_card(
                    country_label, f"{household_price.iloc[-1]:.4f}",
                    f"€/kWh excl. taxes · {household_price.index[-1]}",
                    "win" if (has_hp_b and household_price.iloc[-1] < cmp_household_price.iloc[-1]) else ("loss" if has_hp_b else "neutral")
                ), unsafe_allow_html=True)
            if has_hp_b:
                hp2.markdown(cmp_card(
                    compare_label, f"{cmp_household_price.iloc[-1]:.4f}",
                    f"€/kWh excl. taxes · {cmp_household_price.index[-1]}",
                    "win" if (has_hp_a and cmp_household_price.iloc[-1] < household_price.iloc[-1]) else ("loss" if has_hp_a else "neutral")
                ), unsafe_allow_html=True)
            if has_hp_a and has_hp_b:
                diff_hp = round(household_price.iloc[-1] - cmp_household_price.iloc[-1], 4)
                cheaper = compare_label if diff_hp > 0 else country_label
                hp3.markdown(cmp_card(
                    "Cheaper for Households", cheaper, f"by {abs(diff_hp):.4f} €/kWh",
                    result="overall",
                ), unsafe_allow_html=True)

            st.markdown("")

            fig_hp_cmp = go.Figure()
            if has_hp_a:
                fig_hp_cmp.add_trace(go.Scatter(
                    x=household_price.index, y=household_price.values,
                    name=country_label,
                    line=dict(color="#6366f1", width=2),
                    mode="lines+markers", marker=dict(size=6),
                    hovertemplate="%{x}<br>%{y:.4f} €/kWh<extra>" + country_label + "</extra>",
                ))
            if has_hp_b:
                fig_hp_cmp.add_trace(go.Scatter(
                    x=cmp_household_price.index, y=cmp_household_price.values,
                    name=compare_label,
                    line=dict(color="#f59e0b", width=2),
                    mode="lines+markers", marker=dict(size=6),
                    hovertemplate="%{x}<br>%{y:.4f} €/kWh<extra>" + compare_label + "</extra>",
                ))
            fig_hp_cmp.update_layout(
                title="Household Electricity Price Comparison (€/kWh, excl. taxes)",
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0), height=CH_MD,
                yaxis_title="€/kWh",
                xaxis_title="Semester",
                legend=dict(orientation="h", y=-0.18),
            )
            st.plotly_chart(fig_hp_cmp, width='stretch')
        else:
            st.info("Household electricity price data unavailable for one or both countries.")

        # ── CSV Downloads ──────────────────────────────────────────────────────
        st.divider()
        st.markdown('<div class="section-title">⬇️ Download Comparison Data</div>', unsafe_allow_html=True)
        dl1, dl2 = st.columns(2)
        dl3, dl4 = st.columns(2)

        if import_dep is not None and cmp_import_dep is not None and len(import_dep) > 0 and len(cmp_import_dep) > 0:
            csv_id = pd.DataFrame({
                "Year":                      import_dep.index,
                f"{country_label}_import_dep_pct":  import_dep.values,
                f"{compare_label}_import_dep_pct":  cmp_import_dep.reindex(import_dep.index).values,
            })
            dl1.download_button(
                "📥 Import Dependency",
                csv_id.to_csv(index=False),
                file_name="import_dependency.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t4_import_dep",
            )

        if household_price is not None and cmp_household_price is not None and len(household_price) > 0 and len(cmp_household_price) > 0:
            all_semesters = sorted(set(household_price.index) | set(cmp_household_price.index))
            csv_hp = pd.DataFrame({
                "Semester":                         all_semesters,
                f"{country_label}_eur_kwh":         [household_price.get(s) for s in all_semesters],
                f"{compare_label}_eur_kwh":         [cmp_household_price.get(s) for s in all_semesters],
            })
            dl2.download_button(
                "📥 Household Prices",
                csv_hp.to_csv(index=False),
                file_name="household_electricity_prices.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t4_household",
            )

        if inflation is not None and cmp_inflation is not None:
            cpi_a = inflation["cpi"]
            cpi_b = cmp_inflation["cpi"].reindex(cpi_a.index)
            csv_cpi = pd.DataFrame({
                "Month":                               [str(p) for p in cpi_a.index],
                f"{country_label}_general_cpi_pct":    cpi_a.values,
                f"{compare_label}_general_cpi_pct":    cpi_b.values,
                f"{country_label}_energy_cpi_pct":     inflation["energy"].reindex(cpi_a.index).values,
                f"{compare_label}_energy_cpi_pct":     cmp_inflation["energy"].reindex(cpi_a.index).values,
            })
            dl3.download_button(
                "📥 CPI Comparison",
                csv_cpi.to_csv(index=False),
                file_name="cpi_comparison.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t4_cpi",
            )

        if prices is not None and cmp_prices is not None:
            csv_prices_cmp = pd.DataFrame({
                "Datetime":                     prices.index.astype(str),
                f"{country_label}_eur_mwh":     prices.values,
                f"{compare_label}_eur_mwh":     cmp_prices.reindex(prices.index).values,
            })
            dl4.download_button(
                "📥 Day-Ahead Prices",
                csv_prices_cmp.to_csv(index=False),
                file_name="day_ahead_prices.csv",
                mime="text/csv",
                width='stretch',
                key="dl_t4_prices",
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — SOURCES & DATA
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### 📚 Sources & Data")
    st.markdown("""
    <div class="thesis-box">
    All data used in this dashboard is publicly available from official European
    institutions. No registration is required for Eurostat. ENTSO-E requires a
    free account to obtain an API key.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">⚡ ENTSO-E Transparency Platform</div>', unsafe_allow_html=True)
    st.markdown("""
    The European Network of Transmission System Operators for Electricity (ENTSO-E)
    operates the central transparency platform for European electricity market data.
    """)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Datasets used:**")
        st.markdown("- **Day-ahead prices** — hourly electricity market prices (€/MWh), published daily")
        st.markdown("- **Actual generation per source** — hourly generation by technology (MW), e.g. Solar, Wind, Nuclear, Gas")
        st.markdown("- **Installed generation capacity** — annual snapshot of how much capacity (MW) is installed per source")
        st.markdown("**Update frequency:** Prices and generation are published daily. Installed capacity is annual.")
    with col2:
        st.markdown("**Access:**")
        st.markdown("- Platform: [transparency.entsoe.eu](https://transparency.entsoe.eu)")
        st.markdown("- API docs: [ENTSO-E Restful API Guide](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html)")
        st.markdown("- Python library: [entsoe-py on GitHub](https://github.com/EnergieID/entsoe-py)")
        st.markdown("- **Registration required** — free account at transparency.entsoe.eu, then request an API key via email")
        st.markdown("**Coverage:** EU member states + Norway, Switzerland, Great Britain, and others")

    st.divider()

    st.markdown('<div class="section-title">📊 Eurostat — HICP Inflation (prc_hicp_manr)</div>', unsafe_allow_html=True)
    st.markdown("""
    The Harmonised Index of Consumer Prices (HICP) is the official EU inflation measure,
    compiled by Eurostat. It is harmonised across all EU countries for direct comparability.
    """)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**What we use:**")
        st.markdown("- **CP00** — All items (general CPI) — overall consumer price inflation")
        st.markdown("- **CP04** — Housing, water, electricity, gas and other fuels (energy & housing CPI)")
        st.markdown("- Unit: Annual rate of change (% YoY)")
        st.markdown("**Update frequency:** Monthly, published ~2–3 weeks after the reference month.")
    with col2:
        st.markdown("**Access:**")
        st.markdown("- Dataset: [prc_hicp_manr on Eurostat](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_manr)")
        st.markdown("- API endpoint: `eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr`")
        st.markdown("- No API key required")
        st.markdown("**Coverage:** All EU member states + EEA countries, from 1996 onwards")

    st.divider()

    st.markdown('<div class="section-title">🔌 Eurostat — Household Electricity Prices (nrg_pc_204)</div>', unsafe_allow_html=True)
    st.markdown("""
    Bi-annual survey of electricity prices paid by household consumers,
    reported by national statistical offices to Eurostat.
    """)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**What we use:**")
        st.markdown("- Price per kWh (€/kWh), excluding taxes — more comparable across countries")
        st.markdown("- Consumption band varies by country (the band most representative of national households is used automatically)")
        st.markdown("- Typical bands: <1000 kWh/yr (AT, BE), 1000–2499 kWh/yr (DE, FR), 2500–4999 kWh/yr (PL, CZ)")
        st.markdown("**Update frequency:** Twice a year — S1 (Jan–Jun) published ~end October, S2 (Jul–Dec) published ~end April.")
    with col2:
        st.markdown("**Access:**")
        st.markdown("- Dataset: [nrg_pc_204 on Eurostat](https://ec.europa.eu/eurostat/databrowser/view/nrg_pc_204)")
        st.markdown("- API endpoint: `eurostat/api/dissemination/statistics/1.0/data/nrg_pc_204`")
        st.markdown("- No API key required")
        st.markdown("**Coverage:** EU member states + some candidate countries, from 2007 onwards")
        st.markdown("**Note:** Switzerland, Norway and some non-EU states may have incomplete coverage")

    st.divider()

    st.markdown('<div class="section-title">🛢️ Eurostat — Energy Import Dependency (nrg_ind_id)</div>', unsafe_allow_html=True)
    st.markdown("""
    Annual indicator of what percentage of a country's energy needs are met by imports
    rather than domestic production. The key causal link in this dashboard's thesis.
    """)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**What we use:**")
        st.markdown("- `siec=TOTAL` — all energy products combined (oil, gas, coal, electricity)")
        st.markdown("- Unit: percentage (%). Positive = net importer. Negative = net exporter (e.g. Norway)")
        st.markdown("- Values can exceed 100% for countries that import more than they consume (re-export trade)")
        st.markdown("**Update frequency:** Annual, typically published in the second half of the following year.")
    with col2:
        st.markdown("**Access:**")
        st.markdown("- Dataset: [nrg_ind_id on Eurostat](https://ec.europa.eu/eurostat/databrowser/view/nrg_ind_id)")
        st.markdown("- API endpoint: `eurostat/api/dissemination/statistics/1.0/data/nrg_ind_id`")
        st.markdown("- No API key required")
        st.markdown("**Coverage:** EU member states + EEA and candidate countries, from 1990 onwards")

    st.divider()

    st.markdown('<div class="section-title">🛠️ Technical Stack & Licences</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Libraries used:**")
        st.markdown("- [Streamlit](https://streamlit.io) — dashboard framework (Apache 2.0)")
        st.markdown("- [entsoe-py](https://github.com/EnergieID/entsoe-py) — ENTSO-E API wrapper (MIT)")
        st.markdown("- [Plotly](https://plotly.com/python/) — interactive charts (MIT)")
        st.markdown("- [pandas](https://pandas.pydata.org) — data processing (BSD)")
        st.markdown("- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment variables (BSD)")
    with col2:
        st.markdown("**Data licences:**")
        st.markdown("- ENTSO-E data: [ENTSO-E Terms of Use](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html) — free for non-commercial use with attribution")
        st.markdown("- Eurostat data: [Eurostat copyright notice](https://ec.europa.eu/eurostat/about/policies/copyright) — free reuse with source acknowledgement")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — HOW TO USE
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### ❓ How to Use This Dashboard")
    st.markdown("""
    <div class="thesis-box">
    <strong>Purpose:</strong> This dashboard is designed to help you explore whether — and how much —
    a country's investment in renewable energy has reduced its dependence on fossil fuel imports,
    stabilised its electricity prices, and lowered its energy inflation. Use the tabs to move from
    the long-term structural picture down to short-term market conditions.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">🚀 Getting Started</div>', unsafe_allow_html=True)
    st.markdown("""
    1. **Select a country** in the sidebar under "Primary country"
    2. **Set a date range** — for short and medium-term tabs (Tabs 2 & 3). A range of 1–6 months works well.
    3. **Set the long-term range** using the year slider — this controls Tabs 1 & 4 structural data (5–10 years recommended)
    4. **Click "Fetch Data"** — the app loads all data for your selection. The first fetch may take 10–20 seconds.
    5. **Enable comparison** — toggle "Enable comparison" and select a second country to unlock Tab 4.
    """)

    st.divider()

    st.markdown('<div class="section-title">🌍 Tab 1 — Structural View (Long-term)</div>', unsafe_allow_html=True)
    st.markdown("**What it shows:** Has this country actually committed to renewables structurally?")
    st.markdown("""
    - **Installed Capacity Trend** — the most important structural indicator. This shows how much renewable
      generating capacity (in MW) has been *built* over the years — not what the weather happened to produce.
      A rising renewable share of installed capacity means the country is genuinely investing.
    - **Long-term Inflation** — general CPI vs energy CPI over 5–10 years. A widening gap between energy
      and general inflation suggests energy price shocks are driving overall inflation.
    - **Household Electricity Prices** — what consumers actually pay per kWh (excl. taxes), bi-annually.
      This is more relevant to household welfare than the wholesale market price.
    - **Energy Import Dependency** — what % of total energy is imported. A declining trend here, combined
      with rising renewable capacity, is the clearest evidence of the causal chain at work.
    """)
    st.markdown("""
    <div class="disclaimer">
    ⚠️ Short-term generation data (what was produced last week) reflects weather, not investment.
    Always use installed capacity for structural conclusions.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="section-title">📈 Tab 2 — Market Dynamics (Medium-term)</div>', unsafe_allow_html=True)
    st.markdown("**What it shows:** How the energy market behaves month-to-month.")
    st.markdown("""
    - **Monthly Average Prices** — aggregated from hourly day-ahead data. Shows seasonal patterns and
      longer price trends. Use a date range of at least 3–6 months for meaningful trends.
    - **Monthly Renewable Share** — what fraction of electricity came from renewables each month.
      Note the seasonal patterns: solar peaks in summer, wind in winter in many countries.
    - **Inflation in Period** — CPI filtered to the selected date range for context.
      Energy CPI typically *lags* wholesale price movements by 1–3 months.
    """)

    st.divider()

    st.markdown('<div class="section-title">⚡ Tab 3 — Operational View (Short-term)</div>', unsafe_allow_html=True)
    st.markdown("**What it shows:** Day-to-day electricity market conditions.")
    st.markdown("""
    - **Hourly Price Chart** — every hour of day-ahead prices in the selected range. Useful for spotting
      price spikes, negative prices (when there is excess renewable supply), and daily patterns.
    - **Cheapest & Most Expensive Hours** — practical for understanding when electricity is cheapest.
    - **Price Volatility** — the standard deviation of hourly prices. Higher = more unstable market.
    - **Generation Mix** — what sources produced electricity over the period. Remember this is
      weather-dependent: a windy week will show high wind even in a country with little wind capacity.
    """)

    st.divider()

    st.markdown('<div class="section-title">🔀 Tab 4 — Country Comparison</div>', unsafe_allow_html=True)
    st.markdown("**What it shows:** The full causal chain side by side for two countries.")
    st.markdown("""
    - **Green cards** indicate a better outcome for that country on that metric.
    - **Red cards** indicate a worse outcome.
    - Compare renewable capacity share → import dependency → price volatility → household prices → CPI.
      If the causal chain holds, the country with more renewable capacity should show lower import
      dependency, lower volatility, lower household prices, and lower energy CPI.
    - The **import dependency trend caption** below the chart tells you whether each country is becoming
      more or less energy-independent over the selected period.
    """)

    st.divider()

    st.markdown('<div class="section-title">📐 Understanding the Metrics</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Renewable installed capacity share (%)**")
        st.markdown("Percentage of total installed generating capacity (MW) that comes from renewable sources. *Higher is better for energy independence.*")
        st.markdown("---")
        st.markdown("**Day-ahead price (€/MWh)**")
        st.markdown("The wholesale electricity price set the day before delivery, via market auction. This is what generators and suppliers pay — not directly what households pay.")
        st.markdown("---")
        st.markdown("**Price volatility (std dev, €/MWh)**")
        st.markdown("Standard deviation of hourly prices. A higher number means the market is more unstable — prices swing more widely. Countries with more renewables tend to have lower volatility structurally, but weather effects dominate in short windows.")
        st.markdown("---")
        st.markdown("**Household electricity price (€/kWh, excl. taxes)**")
        st.markdown("What a typical household actually pays per kilowatt-hour, excluding taxes. Bi-annual survey data from Eurostat. More directly relevant to inflation than the wholesale price.")

    with col2:
        st.markdown("**Energy CPI (HICP CP04, % YoY)**")
        st.markdown("Eurostat's harmonised measure of inflation in the energy & housing category. Includes electricity, gas, and other fuels. Directly reflects energy cost pressures on consumers.")
        st.markdown("---")
        st.markdown("**General CPI (HICP CP00, % YoY)**")
        st.markdown("Overall consumer price inflation, harmonised across the EU. Energy is a component of this — when energy CPI falls, it helps pull down general inflation too.")
        st.markdown("---")
        st.markdown("**Energy import dependency (%)**")
        st.markdown("What % of a country's total energy consumption is met by net imports. Positive = importer. Negative = net exporter (e.g. Norway). A declining trend alongside rising renewables is the core causal link this dashboard aims to illustrate.")
        st.markdown("---")
        st.markdown("**ECB 2% target line**")
        st.markdown("The European Central Bank targets 2% annual inflation as its price stability goal. The dashed line on CPI charts marks this threshold.")

    st.divider()

    st.markdown('<div class="section-title">🎨 Energy Source Classification</div>', unsafe_allow_html=True)
    st.markdown("""
    The dashboard classifies every electricity generation source into one of three tiers.
    This classification matters for the causal thesis: only renewables deliver true energy
    independence, while nuclear is a partial solution and fossil fuels are the root of price exposure.
    """)
    cls_col1, cls_col2, cls_col3 = st.columns(3)
    with cls_col1:
        st.markdown(f"""
        <div style='border-left:4px solid {TIER_COLORS["renewable"]}; padding:0.6rem 1rem; background:#0a1f12; border-radius:6px; height:100%;'>
            <strong style='color:{TIER_COLORS["renewable"]}'>🌱 Renewable</strong><br>
            <span style='font-size:0.85rem; color:#bbf7d0;'>Solar · Wind · Hydro · Biomass · Geothermal · Marine · Waste</span><br><br>
            <span style='font-size:0.8rem; color:#9ca3af;'>
            Domestic, zero fuel imports, no exposure to global fuel prices.
            <strong>Truly energy-independent.</strong>
            </span>
        </div>
        """, unsafe_allow_html=True)
    with cls_col2:
        st.markdown(f"""
        <div style='border-left:4px solid {TIER_COLORS["nuclear"]}; padding:0.6rem 1rem; background:#1e1b3d; border-radius:6px; height:100%;'>
            <strong style='color:{TIER_COLORS["nuclear"]}'>⚛️ Nuclear</strong><br>
            <span style='font-size:0.85rem; color:#e9d5ff;'>Nuclear (uranium-fuelled fission)</span><br><br>
            <span style='font-size:0.8rem; color:#9ca3af;'>
            Low-carbon but NOT renewable. Uranium is imported (Kazakhstan, Niger, Canada, Australia).
            Fuel cost is only ~5% of price, so price exposure is low —
            but <strong>still import-dependent</strong>.
            </span>
        </div>
        """, unsafe_allow_html=True)
    with cls_col3:
        st.markdown(f"""
        <div style='border-left:4px solid {TIER_COLORS["fossil"]}; padding:0.6rem 1rem; background:#2d0a14; border-radius:6px; height:100%;'>
            <strong style='color:{TIER_COLORS["fossil"]}'>🛢️ Fossil</strong><br>
            <span style='font-size:0.85rem; color:#fecaca;'>Gas · Hard coal · Lignite · Oil · Peat</span><br><br>
            <span style='font-size:0.8rem; color:#9ca3af;'>
            High-carbon, fully import-dependent for most European countries.
            Fuel cost is ~60–80% of electricity price — <strong>direct exposure to global fuel price shocks</strong>.
            </span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("")
    st.caption(
        "💡 Why this matters: France looks energy-independent on the import dependency chart because of nuclear, "
        "but it still imports 100% of its uranium. The dashboard treats nuclear honestly — it's neither renewable "
        "nor as exposed as fossil fuels, but it's not the same as wind or solar."
    )

    st.divider()

    st.markdown('<div class="section-title">⚠️ Important Limitations</div>', unsafe_allow_html=True)
    st.markdown("""
    This dashboard is designed to *illustrate* a causal mechanism — not to definitively *prove* it.
    Keep these limitations in mind when interpreting the data:
    """)
    st.markdown("""
    - **Market design varies** — some electricity markets are structurally more coupled to gas prices
      (e.g. Spain, Italy) due to how their merit-order pricing works, regardless of renewable share.
    - **Short-term generation ≠ structural investment** — a week of cloudy, windless weather can make
      a highly renewable country look fossil-heavy. Always use installed capacity for structural conclusions.
    - **CPI has many drivers** — wages, import costs, monetary policy, taxes, and supply chains all affect
      inflation independently of energy. The energy–CPI link is real but partial.
    - **Data quality varies** — ENTSO-E installed capacity data is incomplete or missing for some countries.
      A disclaimer is shown where data may be unreliable.
    - **Consumption band comparability** — household electricity prices use different consumption bands
      per country (Eurostat reporting varies). Cross-country comparisons should be made with care.
    """)


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style='font-size:0.72rem; color:#4b5563; font-family: DM Mono, monospace; line-height:1.8; text-align:center'>
Data: ENTSO-E Transparency Platform · Eurostat HICP · Built with Streamlit<br>
Note: Electricity market design varies by country · CPI is influenced by many factors beyond energy ·
Short-term generation reflects weather, not structural investment
</div>
""", unsafe_allow_html=True)
