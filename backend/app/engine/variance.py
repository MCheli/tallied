"""
Variance analysis — compare plan projections and forecasts against actuals.

Pure computation, no framework dependencies.
"""

from __future__ import annotations

from typing import Any

_BUCKETS = ("cash", "investments", "company_stock", "home_equity", "retirement_bal", "net_worth")


def _pct_var(actual: float, reference: float) -> float | None:
    """Percentage variance of *actual* vs *reference*. None if reference is zero."""
    if reference == 0:
        return None
    return round((actual - reference) / abs(reference), 4)


def _row_to_dict(row: Any) -> dict:
    """Accept a ProjectionRow, plain dict, or dataclass and return a dict."""
    if isinstance(row, dict):
        return row
    # dataclass or namedtuple
    if hasattr(row, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(row)
    return dict(row)


def _index_by_year(rows: list) -> dict[int, dict]:
    """Index a list of row-likes by their 'year' key."""
    result: dict[int, dict] = {}
    for r in rows:
        d = _row_to_dict(r)
        y = d.get("year")
        if y is not None:
            result[int(y)] = d
    return result


def compute_variance(
    plan_projections: list[dict | Any],
    actuals: list[dict | Any],
    forecasts: list[dict | Any] | None = None,
) -> list[dict]:
    """
    For each actual snapshot, find matching year in plan_projections (and optionally
    forecasts).  Compute variance for each of the five balance buckets plus net_worth.

    Parameters
    ----------
    plan_projections : list
        Rows from the projection engine (ProjectionRow or dicts).
    actuals : list
        Observed snapshots with at least ``year`` and the bucket fields.
    forecasts : list | None
        Optional revised forecast rows (same shape as plan_projections).

    Returns
    -------
    list[dict]
        One entry per year present in *actuals*, ordered by year.

        Each entry::

            {
                "year": 2026,
                "metrics": {
                    "cash": {
                        "plan": 50000,
                        "forecast": 52000,   # None if no forecast
                        "actual": 53000,
                        "plan_var_pct": 0.06,
                        "forecast_var_pct": 0.019,
                    },
                    ...
                }
            }
    """
    plan_idx = _index_by_year(plan_projections)
    forecast_idx = _index_by_year(forecasts) if forecasts else {}
    actual_idx = _index_by_year(actuals)

    results: list[dict] = []

    for year in sorted(actual_idx):
        act = actual_idx[year]
        plan = plan_idx.get(year, {})
        forecast = forecast_idx.get(year, {})

        metrics: dict[str, dict] = {}
        for bucket in _BUCKETS:
            actual_val = act.get(bucket)
            plan_val = plan.get(bucket)
            forecast_val = forecast.get(bucket) if forecast else None

            if actual_val is None:
                continue

            entry: dict[str, Any] = {
                "plan": plan_val,
                "forecast": forecast_val,
                "actual": actual_val,
                "plan_var_pct": _pct_var(actual_val, plan_val) if plan_val is not None else None,
                "forecast_var_pct": (
                    _pct_var(actual_val, forecast_val)
                    if forecast_val is not None
                    else None
                ),
            }
            metrics[bucket] = entry

        results.append({"year": year, "metrics": metrics})

    return results
