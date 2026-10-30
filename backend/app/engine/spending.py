"""
Spending analysis — category totals, recurring expense detection, monthly totals.

Pure computation, no framework dependencies.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median


def _month_key(date_str: str) -> str:
    """Extract 'YYYY-MM' from an ISO-ish date string."""
    return date_str[:7]


def _in_range(date_str: str, from_date: str | None, to_date: str | None) -> bool:
    """Check whether *date_str* falls within [from_date, to_date] (inclusive)."""
    if from_date and date_str < from_date:
        return False
    return not (to_date and date_str > to_date)


def spending_by_category(
    transactions: list[dict],
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """
    Group transactions by category and return totals sorted by absolute amount
    (largest spend first).

    Parameters
    ----------
    transactions : list[dict]
        Each dict must contain:
          - date : str (ISO date)
          - amount : float (negative = expense, positive = income)
          - category : str
    from_date, to_date : str | None
        Optional ISO date bounds (inclusive).

    Returns
    -------
    list[dict]
        [{"category": "Groceries", "total": -1200.50, "count": 45}, ...]
        Sorted by ascending total (most negative first = biggest spend).
    """
    cat_total: dict[str, float] = defaultdict(float)
    cat_count: dict[str, int] = defaultdict(int)

    for t in transactions:
        if not _in_range(t["date"], from_date, to_date):
            continue
        cat = t.get("category", "Uncategorized")
        cat_total[cat] += t["amount"]
        cat_count[cat] += 1

    results = [
        {"category": cat, "total": round(cat_total[cat], 2), "count": cat_count[cat]}
        for cat in cat_total
    ]
    results.sort(key=lambda r: r["total"])  # most negative (biggest spend) first
    return results


# Habits, not bills: a coffee shop visited every month is not a recurring expense.
NOT_RECURRING_CATEGORIES = frozenset({
    "Restaurants", "Fast Food", "Food Delivery", "Coffee Shops", "Groceries", "Gas", "Shopping", "Parking",
    "Camping", "Travel", "Hotels",
})


def detect_recurring(transactions: list[dict], as_of: str, *, min_months: int = 3) -> list[dict]:
    """
    Bills and subscriptions: merchants charged about once a month at a steady amount, still active.

    A merchant qualifies when it was charged in at least ``min_months`` distinct months, at most twice a
    month on average (two phone lines still count; daily parking does not), with at least 60 percent of
    charges within 25 percent of the median, and a charge within 45 days of ``as_of``. Merchants are
    grouped by name only; the category shown is the most common one. Categories in
    NOT_RECURRING_CATEGORIES are habits and never qualify.

    Parameters
    ----------
    transactions : list[dict]
        Each dict must contain:
          - date : str (ISO date)
          - amount : float (negative = expense)
          - merchant : str
          - category : str  (optional, defaults to "Uncategorized")
    as_of : str (ISO date)
        End of the period; a merchant with no charge in the 45 days before it has stopped.

    Returns
    -------
    list[dict]
        Sorted by monthly cost (most expensive first). avg_monthly is the merchant's total over the
        months from its first to its last charge, so it is what the bill costs a month.
        [{"merchant": "Spotify", "category": "Streaming", "avg_monthly": -21.99,
          "months_seen": 3, "last_date": "2026-10-01"}, ...]
    """
    from datetime import date, timedelta

    cutoff = (date.fromisoformat(as_of[:10]) - timedelta(days=45)).isoformat()
    merchant_data: dict[str, list[dict]] = defaultdict(list)
    for t in transactions:
        if t["amount"] >= 0 or not t.get("merchant"):
            continue
        merchant_data[t["merchant"]].append({
            "month": _month_key(t["date"]),
            "amount": abs(t["amount"]),
            "date": t["date"],
            "category": t.get("category") or "Uncategorized",
        })

    results: list[dict] = []
    for merchant, entries in merchant_data.items():
        months = sorted({e["month"] for e in entries})
        if len(months) < min_months or len(entries) > 2 * len(months):
            continue
        last_date = max(e["date"] for e in entries)
        if last_date < cutoff:
            continue
        cat_counts: dict[str, int] = defaultdict(int)
        for e in entries:
            cat_counts[e["category"]] += 1
        category = max(cat_counts, key=cat_counts.get)  # type: ignore[arg-type]
        if category in NOT_RECURRING_CATEGORIES:
            continue
        amounts = [e["amount"] for e in entries]
        med = median(amounts)
        if med == 0 or sum(1 for a in amounts if abs(a - med) / med <= 0.25) / len(amounts) < 0.6:
            continue
        (y0, m0), (y1, m1) = (map(int, months[0].split("-")), map(int, months[-1].split("-")))
        span = (y1 - y0) * 12 + (m1 - m0) + 1
        results.append({
            "merchant": merchant,
            "category": category,
            "avg_monthly": round(-sum(amounts) / span, 2),
            "months_seen": len(months),
            "last_date": last_date,
        })

    results.sort(key=lambda r: r["avg_monthly"])
    return results


def monthly_spending_totals(transactions: list[dict]) -> list[dict]:
    """
    Monthly total spending (expenses only — negative amounts).

    Parameters
    ----------
    transactions : list[dict]
        Each dict must contain:
          - date : str (ISO date)
          - amount : float

    Returns
    -------
    list[dict]
        Sorted chronologically.
        [{"month": "2025-01", "total": -4500.00, "count": 87}, ...]
    """
    month_total: dict[str, float] = defaultdict(float)
    month_count: dict[str, int] = defaultdict(int)

    for t in transactions:
        amount = t["amount"]
        if amount >= 0:
            continue  # skip income / credits
        month = _month_key(t["date"])
        month_total[month] += amount
        month_count[month] += 1

    results = [
        {"month": m, "total": round(month_total[m], 2), "count": month_count[m]}
        for m in sorted(month_total)
    ]
    return results
