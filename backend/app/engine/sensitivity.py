"""
Sensitivity analysis — bump each assumption ±1 unit, measure impact on net worth.

Pure computation, depends only on projection.py.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from .projection import ProjectionAssumptions, ProjectionInput, run_projection


# Each entry: (field_name, display_name, bump_amount)
_SENSITIVITY_PARAMS: list[tuple[str, str, float]] = [
    ("retirement_age",        "Retirement Age",              2),
    ("total_comp_growth",     "Total Comp Growth",           0.01),
    ("rsu_pct_of_comp",       "RSU % of Comp",               0.05),
    ("rsu_tax_rate",          "RSU Tax Rate",                0.05),
    ("investment_return",     "Pre-Retirement Return",       0.01),
    ("retirement_return",     "Post-Retirement Return",      0.01),
    ("stock_price_growth",    "Stock Price Growth",          0.01),
    ("inflation",             "Inflation",                   0.01),
    ("home_appreciation",     "Home Appreciation",           0.01),
    ("monthly_cash_savings",  "Monthly Cash Savings",        200.0),
    ("retirement_spending",   "Retirement Spending",         10_000.0),
    ("retirement_tax_rate",   "Retirement Tax Rate",         0.05),
]


def _net_worth_at_year(rows: list, year: int) -> float:
    """Return net_worth from the projection row matching *year*, or the last row."""
    for r in rows:
        if r.year == year:
            return r.net_worth
    # Fallback: last row
    return rows[-1].net_worth if rows else 0.0


def _make_bumped(base: ProjectionAssumptions, key: str, delta: float) -> ProjectionAssumptions:
    """Return a copy of *base* with *key* adjusted by *delta*."""
    d = asdict(base)
    d[key] = d[key] + delta
    return ProjectionAssumptions(**d)


def run_sensitivity(
    inputs: ProjectionInput,
    base_assumptions: ProjectionAssumptions,
    target_year: int | None = None,
) -> list[dict]:
    """
    For each tuneable assumption, bump up and down, rerun the projection,
    and measure the change in net_worth at *target_year*.

    Parameters
    ----------
    inputs : ProjectionInput
        Current financial state.
    base_assumptions : ProjectionAssumptions
        Baseline assumptions.
    target_year : int | None
        Year at which to compare net_worth.  Defaults to the retirement year.

    Returns
    -------
    list[dict]
        Sorted by descending absolute impact (max of |low|, |high|).
        Each dict:
          key, display_name, base_value, bump, impact_low, impact_high
    """
    if target_year is None:
        target_year = inputs.current_year + (base_assumptions.retirement_age - inputs.current_age)

    baseline_rows = run_projection(inputs, base_assumptions)
    baseline_nw = _net_worth_at_year(baseline_rows, target_year)

    results: list[dict] = []

    for key, display_name, bump in _SENSITIVITY_PARAMS:
        base_value = getattr(base_assumptions, key)

        # --- low scenario ---
        low_assumptions = _make_bumped(base_assumptions, key, -bump)
        low_rows = run_projection(inputs, low_assumptions)
        low_nw = _net_worth_at_year(low_rows, target_year)

        # --- high scenario ---
        high_assumptions = _make_bumped(base_assumptions, key, bump)
        high_rows = run_projection(inputs, high_assumptions)
        high_nw = _net_worth_at_year(high_rows, target_year)

        results.append({
            "key": key,
            "display_name": display_name,
            "base_value": base_value,
            "bump": bump,
            "impact_low": round(low_nw - baseline_nw, 2),
            "impact_high": round(high_nw - baseline_nw, 2),
        })

    # Sort by largest absolute impact (take the bigger of the two sides)
    results.sort(key=lambda r: max(abs(r["impact_low"]), abs(r["impact_high"])), reverse=True)
    return results
