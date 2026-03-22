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
    if to_date and date_str > to_date:
        return False
    return True


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


def detect_recurring(transactions: list[dict]) -> list[dict]:
    """
    Detect recurring expenses by finding merchants that appear in 3+ distinct
    months with similar amounts (within 20 % of median).

    Parameters
    ----------
    transactions : list[dict]
        Each dict must contain:
          - date : str (ISO date)
          - amount : float (negative = expense)
          - merchant : str
          - category : str  (optional, defaults to "Uncategorized")

    Returns
    -------
    list[dict]
        Sorted by average monthly amount (most expensive first).
        [
            {
                "merchant": "Spotify",
                "category": "Subscriptions",
                "avg_monthly": -15.99,
                "months_seen": 12,
                "last_date": "2026-03-01",
            },
            ...
        ]
    """
    # Collect (month, amount, date, category) per merchant
    merchant_data: dict[str, list[dict]] = defaultdict(list)

    for t in transactions:
        amount = t["amount"]
        if amount >= 0:
            continue  # only look at expenses
        merchant = t.get("merchant", "")
        if not merchant:
            continue
        merchant_data[merchant].append({
            "month": _month_key(t["date"]),
            "amount": amount,
            "date": t["date"],
            "category": t.get("category", "Uncategorized"),
        })

    results: list[dict] = []

    for merchant, entries in merchant_data.items():
        # Distinct months
        months = {e["month"] for e in entries}
        if len(months) < 3:
            continue

        amounts = [abs(e["amount"]) for e in entries]
        med = median(amounts)
        if med == 0:
            continue

        # Check that most entries are within 20% of the median
        within = sum(1 for a in amounts if abs(a - med) / med <= 0.20)
        if within / len(amounts) < 0.6:
            continue  # too much variance — probably not recurring

        # Use the most common category
        cat_counts: dict[str, int] = defaultdict(int)
        for e in entries:
            cat_counts[e["category"]] += 1
        category = max(cat_counts, key=cat_counts.get)  # type: ignore[arg-type]

        last_date = max(e["date"] for e in entries)

        results.append({
            "merchant": merchant,
            "category": category,
            "avg_monthly": round(-med, 2),  # negative to match expense convention
            "months_seen": len(months),
            "last_date": last_date,
        })

    # Sort by avg_monthly ascending (most negative = biggest spend first)
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
