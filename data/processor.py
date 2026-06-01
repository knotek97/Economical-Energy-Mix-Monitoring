"""
processor.py — calculations, sorting, and derived metrics
"""

import pandas as pd
import numpy as np


# ── Price analytics ───────────────────────────────────────────────────────────
def price_summary(prices: pd.Series) -> dict:
    """Key statistics for a price series."""
    return {
        "mean":   round(prices.mean(), 2),
        "median": round(prices.median(), 2),
        "min":    round(prices.min(), 2),
        "max":    round(prices.max(), 2),
        "std":    round(prices.std(), 2),
    }


def cheapest_hours(prices: pd.Series, n: int = 5) -> pd.Series:
    """Return the n cheapest hours, sorted ascending."""
    return prices.nsmallest(n).sort_index()


def most_expensive_hours(prices: pd.Series, n: int = 5) -> pd.Series:
    """Return the n most expensive hours, sorted ascending."""
    return prices.nlargest(n).sort_index()


def daily_avg_prices(prices: pd.Series) -> pd.Series:
    """Resample hourly prices to daily averages."""
    return prices.resample("D").mean().round(2)


def monthly_avg_prices(prices: pd.Series) -> pd.Series:
    """
    Resample hourly prices to monthly averages.
    Useful for medium-term trend view (1-2 years).
    """
    return prices.resample("ME").mean().round(2)


def price_volatility(prices: pd.Series) -> float:
    """
    Standard deviation of hourly prices over the period (€/MWh).

    This is a better indicator than correlation for comparing countries:
    - Lower volatility = more stable energy market
    - Countries with high renewable share tend to have structurally lower
      volatility over time (less exposure to fossil fuel price swings)
    """
    return round(float(prices.std()), 2)


# ── Generation analytics ──────────────────────────────────────────────────────
# Three-tier classification used throughout the dashboard.
#
# RENEWABLE — truly energy-independent: no fuel imports, no fuel-price exposure.
#             Sun, wind, water, biomass and geothermal are domestic and free.
#
# NUCLEAR  — low-carbon but NOT energy-independent. Almost every European nuclear
#            country imports 100% of its uranium (Kazakhstan, Niger, Canada,
#            Australia). Uranium IS counted in Eurostat's import dependency.
#            However, fuel cost is only ~5% of the electricity price (vs ~60–80%
#            for gas), so price exposure to fuel markets is much lower than fossil.
#
# FOSSIL  — high-carbon, fully import-dependent for most European countries.
#            Direct exposure to global gas, coal, and oil price shocks.
RENEWABLE_SOURCES = {
    "Solar",
    "Wind Onshore",
    "Wind Offshore",
    "Hydro Run-of-river and poundage",
    "Hydro Water Reservoir",
    "Hydro Pumped Storage",
    "Geothermal",
    "Other renewable",
    "Biomass",
    "Marine",
    "Waste",
}

NUCLEAR_SOURCES = {
    "Nuclear",
}

FOSSIL_SOURCES = {
    "Fossil Gas",
    "Fossil Hard coal",
    "Fossil Brown coal/Lignite",
    "Fossil Oil",
    "Fossil Oil shale",
    "Fossil Peat",
    "Fossil Coal-derived gas",
}


def classify_source(source_name: str) -> str:
    """
    Return the tier ('renewable', 'nuclear', 'fossil', or 'other') for a
    given ENTSO-E generation source name.
    """
    if source_name in RENEWABLE_SOURCES:
        return "renewable"
    if source_name in NUCLEAR_SOURCES:
        return "nuclear"
    if source_name in FOSSIL_SOURCES:
        return "fossil"
    return "other"


# Colours used consistently across the dashboard for each tier
TIER_COLORS = {
    "renewable": "#16a34a",   # green-600 — clear, accessible on white
    "nuclear":   "#7c3aed",   # violet-600 — distinct from green, readable
    "fossil":    "#dc2626",   # red-600 — clear warning colour
    "other":     "#6b7280",   # gray-500
}


# ── CO₂ emission factors ──────────────────────────────────────────────────────
# Lifecycle greenhouse gas emission factors in gCO₂-equivalent per kWh.
# Source: IPCC AR5 (2014) Annex III, median lifecycle values, widely used in
# academic and policy work. These are ESTIMATES — actual emissions vary by
# plant age, fuel quality, and methodology (direct combustion vs full lifecycle).
#
# Presented as "estimated carbon intensity" — not measured emissions.
# Biomass is contested (counted as ~230 here; some methodologies treat it as
# near-zero under carbon-neutrality assumptions, others much higher).
EMISSION_FACTORS = {
    # Renewables — low lifecycle emissions (manufacturing, construction)
    "Solar":                            48,
    "Wind Onshore":                     11,
    "Wind Offshore":                    12,
    "Hydro Run-of-river and poundage":  24,
    "Hydro Water Reservoir":            24,
    "Hydro Pumped Storage":             24,
    "Geothermal":                       38,
    "Marine":                           17,
    "Biomass":                          230,   # contested — lifecycle estimate
    "Waste":                            580,   # waste incineration
    "Other renewable":                  100,
    # Nuclear — very low lifecycle emissions
    "Nuclear":                          12,
    # Fossil — high direct-combustion emissions
    "Fossil Gas":                       490,
    "Fossil Coal-derived gas":          490,
    "Fossil Hard coal":                 820,
    "Fossil Brown coal/Lignite":        1050,
    "Fossil Oil":                       650,
    "Fossil Oil shale":                 900,
    "Fossil Peat":                      750,
    # Fallback for unmapped sources
    "Other":                            300,
}

# Default factor for any source not in the table (conservative mid-range)
DEFAULT_EMISSION_FACTOR = 300


def carbon_intensity(gen: pd.DataFrame) -> float | None:
    """
    Estimated carbon intensity of electricity generation in gCO₂/kWh,
    weighted by each source's share of total generation over the period.

    Returns None if no generation data. Otherwise a single weighted-average
    figure for the whole period.

    Methodology: Σ(generation_source × factor_source) / Σ(generation_total)
    """
    if gen is None or gen.empty:
        return None
    totals = gen.sum()           # total MWh per source over the period
    total_gen = totals.sum()
    if total_gen <= 0:
        return None
    weighted = sum(
        totals[src] * EMISSION_FACTORS.get(src, DEFAULT_EMISSION_FACTOR)
        for src in totals.index
    )
    return round(weighted / total_gen, 1)


def carbon_intensity_series(gen: pd.DataFrame, freq: str = "D") -> pd.Series:
    """
    Carbon intensity over time (gCO₂/kWh) resampled at the given frequency.
    Useful for showing how grid carbon intensity varies day to day with the
    generation mix (e.g. low on windy days, high when gas ramps up).

    freq: pandas resample frequency — "D" daily, "ME" monthly, "h" hourly.
    """
    if gen is None or gen.empty:
        return pd.Series(dtype=float)

    factors = pd.Series(
        {src: EMISSION_FACTORS.get(src, DEFAULT_EMISSION_FACTOR) for src in gen.columns}
    )
    resampled = gen.resample(freq).sum()
    total     = resampled.sum(axis=1)
    weighted  = (resampled * factors).sum(axis=1)
    intensity = (weighted / total).round(1)
    return intensity[total > 0]


def carbon_intensity_band(intensity: float) -> tuple[str, str]:
    """
    Classify a carbon intensity value into a descriptive band + colour.
    Bands roughly follow ElectricityMaps / Ember conventions.

    Returns (label, hex_colour).
    """
    if intensity is None:
        return ("Unknown", "#6b7280")
    if intensity < 100:
        return ("Very low", "#16a34a")     # green
    if intensity < 250:
        return ("Low", "#65a30d")          # lime
    if intensity < 400:
        return ("Moderate", "#ca8a04")     # amber
    if intensity < 600:
        return ("High", "#ea580c")         # orange
    return ("Very high", "#dc2626")        # red


def total_by_source(gen: pd.DataFrame) -> pd.Series:
    """Total generation (MWh) per source, sorted descending."""
    totals = gen.sum().sort_values(ascending=False)
    return totals.round(0)


def renewable_share(gen: pd.DataFrame) -> float:
    """
    Percentage of total generation that comes from renewable sources only.
    Excludes nuclear (which is low-carbon but not renewable).
    """
    cols_renewable = [c for c in gen.columns if c in RENEWABLE_SOURCES]
    if not cols_renewable:
        return 0.0
    total    = gen.sum().sum()
    re_total = gen[cols_renewable].sum().sum()
    return round((re_total / total) * 100, 1) if total > 0 else 0.0


def nuclear_share(gen: pd.DataFrame) -> float:
    """Percentage of total generation that comes from nuclear."""
    cols_nuclear = [c for c in gen.columns if c in NUCLEAR_SOURCES]
    if not cols_nuclear:
        return 0.0
    total    = gen.sum().sum()
    nu_total = gen[cols_nuclear].sum().sum()
    return round((nu_total / total) * 100, 1) if total > 0 else 0.0


def fossil_share(gen: pd.DataFrame) -> float:
    """Percentage of total generation that comes from fossil sources."""
    cols_fossil = [c for c in gen.columns if c in FOSSIL_SOURCES]
    if not cols_fossil:
        return 0.0
    total    = gen.sum().sum()
    fo_total = gen[cols_fossil].sum().sum()
    return round((fo_total / total) * 100, 1) if total > 0 else 0.0


def low_carbon_share(gen: pd.DataFrame) -> float:
    """
    Percentage of total generation from low-carbon sources (renewable + nuclear).
    Useful for climate-focused metrics, but does NOT imply energy independence —
    nuclear still requires uranium imports.
    """
    return round(renewable_share(gen) + nuclear_share(gen), 1)


def tier_shares(gen: pd.DataFrame) -> dict:
    """
    Return all three tier shares plus 'other' as a single dict.
    Useful for stacked bars and tier-level pie charts.
    """
    return {
        "renewable": renewable_share(gen),
        "nuclear":   nuclear_share(gen),
        "fossil":    fossil_share(gen),
        "other":     round(100 - renewable_share(gen) - nuclear_share(gen) - fossil_share(gen), 1),
    }


def monthly_renewable_share(gen: pd.DataFrame) -> pd.Series:
    """
    Renewable generation share per month (%).
    Useful for medium-term trend view — shows seasonal patterns and
    whether renewable output is growing month over month.

    Note: this reflects weather + capacity. Use installed capacity data
    from fetcher.py for the structural (investment) picture.
    Excludes nuclear from the numerator.
    """
    re_cols = [c for c in gen.columns if c in RENEWABLE_SOURCES]
    if not re_cols:
        return pd.Series(dtype=float)

    monthly_total = gen.resample("ME").sum().sum(axis=1)
    monthly_re    = gen[re_cols].resample("ME").sum().sum(axis=1)

    share = (monthly_re / monthly_total * 100).round(1)
    share = share[monthly_total > 0]
    return share


def generation_mix_pct(gen: pd.DataFrame) -> pd.Series:
    """Each source as a percentage of total generation."""
    totals = gen.sum()
    pct    = (totals / totals.sum() * 100).round(1)
    return pct.sort_values(ascending=False)


def daily_avg_generation(gen: pd.DataFrame) -> pd.DataFrame:
    """Resample to daily averages per source."""
    return gen.resample("D").mean().round(1)


def top_sources(gen: pd.DataFrame, n: int = 5) -> pd.Series:
    """The n largest generation sources by total output."""
    return total_by_source(gen).head(n)


# ── Combined / derived ────────────────────────────────────────────────────────
def price_generation_correlation(
    prices: pd.Series, gen: pd.DataFrame
) -> pd.Series:
    """
    Pearson correlation between hourly prices and each generation source.

    Kept for reference, but prefer price_volatility() for country comparisons —
    volatility is a cleaner indicator that avoids implying direct causality
    from short-term data.
    """
    combined = gen.copy()
    combined["Price"] = prices
    combined = combined.dropna()
    corr = combined.corr()["Price"].drop("Price").sort_values()
    return corr.round(3)
