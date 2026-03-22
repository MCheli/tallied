"""Generate trend-based forecasts from historical balance data."""
from datetime import datetime
from dataclasses import dataclass


@dataclass
class ForecastRow:
    year: int
    cash: float
    investments: float
    company_stock: float
    home_equity: float
    retirement_bal: float
    net_worth: float


# Map display_groups to forecast buckets
GROUP_TO_BUCKET: dict[str, str] = {
    "Cash": "cash",
    "Investments": "investments",
    "Home Equity": "home_equity",
    "Retirement": "retirement_bal",
    "Credit Cards": "_subtract_cash",
    "Other Loans": "_subtract_cash",
}


def _linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Simple OLS: returns (slope, intercept) for y = slope*x + intercept."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return 0.0, ys[0]

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)

    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-10:
        return 0.0, sum_y / n

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def generate_forecast(
    balance_history: list[dict],  # [{date, display_group, total}]
    years_forward: int = 5,
) -> list[ForecastRow]:
    """
    Simple linear trend extrapolation from historical monthly averages.
    Groups data by display_group, fits a linear trend to monthly totals,
    and projects forward.
    """
    if not balance_history:
        return []

    # Group by display_group, then by (year, month) -> sum of balances
    # Each entry: {date: "YYYY-MM-DD", display_group: str, total: float}
    group_monthly: dict[str, dict[str, list[float]]] = {}

    for row in balance_history:
        dg = row.get("display_group", "Other")
        dt_str = str(row.get("date", ""))
        total = float(row.get("total", 0))

        if not dt_str or len(dt_str) < 7:
            continue

        month_key = dt_str[:7]  # "YYYY-MM"

        if dg not in group_monthly:
            group_monthly[dg] = {}
        if month_key not in group_monthly[dg]:
            group_monthly[dg][month_key] = []
        group_monthly[dg][month_key].append(total)

    if not group_monthly:
        return []

    # For each display_group, compute monthly averages and fit trend
    # Use months since epoch as x-axis for regression
    bucket_trends: dict[str, tuple[float, float]] = {}  # bucket -> (slope, intercept)

    # Find latest month across all groups
    all_months: set[str] = set()
    for months in group_monthly.values():
        all_months.update(months.keys())

    if not all_months:
        return []

    sorted_months = sorted(all_months)
    latest_month = sorted_months[-1]
    latest_year = int(latest_month[:4])
    latest_mo = int(latest_month[5:7])

    def month_to_x(month_key: str) -> float:
        """Convert YYYY-MM to months since 2000-01."""
        y = int(month_key[:4])
        m = int(month_key[5:7])
        return (y - 2000) * 12 + m

    for display_group, months_data in group_monthly.items():
        bucket = GROUP_TO_BUCKET.get(display_group)
        if bucket is None:
            continue

        # Monthly averages (take the last balance per month as the representative)
        xs: list[float] = []
        ys: list[float] = []
        for month_key in sorted(months_data.keys()):
            vals = months_data[month_key]
            # Use the average of all balances in this month
            avg = sum(vals) / len(vals)
            xs.append(month_to_x(month_key))
            ys.append(avg)

        if not xs:
            continue

        slope, intercept = _linear_regression(xs, ys)

        if bucket == "_subtract_cash":
            # Debts subtract from cash
            existing = bucket_trends.get("cash", (0.0, 0.0))
            bucket_trends["cash"] = (
                existing[0] - slope,
                existing[1] - intercept,
            )
        else:
            existing = bucket_trends.get(bucket, (0.0, 0.0))
            bucket_trends[bucket] = (
                existing[0] + slope,
                existing[1] + intercept,
            )

    # Project forward from current year
    current_year = latest_year
    rows: list[ForecastRow] = []

    for yr_offset in range(years_forward + 1):
        year = current_year + yr_offset
        # Project to December of each year
        future_x = month_to_x(f"{year}-12")

        values: dict[str, float] = {}
        for bucket in ["cash", "investments", "company_stock", "home_equity", "retirement_bal"]:
            slope, intercept = bucket_trends.get(bucket, (0.0, 0.0))
            projected = slope * future_x + intercept
            values[bucket] = round(projected, 2)

        net_worth = sum(values.values())

        rows.append(ForecastRow(
            year=year,
            cash=values["cash"],
            investments=values["investments"],
            company_stock=values.get("company_stock", 0.0),
            home_equity=values["home_equity"],
            retirement_bal=values["retirement_bal"],
            net_worth=round(net_worth, 2),
        ))

    return rows
