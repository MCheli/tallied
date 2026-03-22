"""
Cash flow computation from consecutive balance snapshots.

Pure computation, no framework dependencies.
"""

from __future__ import annotations

from collections import defaultdict


def _month_key(date_str: str) -> str:
    """Extract 'YYYY-MM' from an ISO-ish date string."""
    return date_str[:7]


def compute_cash_flow(snapshots: list[dict]) -> list[dict]:
    """
    Compute monthly cash flow as balance changes between consecutive snapshots.
    Group by display_group.

    Parameters
    ----------
    snapshots : list[dict]
        Each dict must contain:
          - account_id : str | int
          - display_group : str
          - snapshot_date : str  (ISO date)
          - balance : float

    Returns
    -------
    list[dict]
        Sorted by month, one entry per month (starting from the *second* month).
        Each dict::

            {"month": "2025-03", "Cash": 500.0, "Investments": 2000.0, ..., "total": 2500.0}

    Notes
    -----
    - Uses the last balance per account per month.
    - Cash flow is defined as the change in balance from one month to the next.
    - Positive values = balance increased; negative = decreased.
    - The first month has no prior reference, so it is omitted.
    """
    if not snapshots:
        return []

    # ------------------------------------------------------------------ #
    # 1.  Last balance per (account, month)
    # ------------------------------------------------------------------ #
    last_per_acct_month: dict[tuple, tuple[str, float]] = {}
    account_group: dict = {}

    for s in snapshots:
        acct = s["account_id"]
        month = _month_key(s["snapshot_date"])
        date = s["snapshot_date"]
        balance = s["balance"]
        key = (acct, month)
        prev = last_per_acct_month.get(key)
        if prev is None or date > prev[0]:
            last_per_acct_month[key] = (date, balance)
        account_group[acct] = s["display_group"]

    # ------------------------------------------------------------------ #
    # 2.  Sorted months and accounts
    # ------------------------------------------------------------------ #
    all_months = sorted({k[1] for k in last_per_acct_month})
    all_accounts = sorted(account_group.keys(), key=str)
    all_groups = sorted(set(account_group.values()))

    if len(all_months) < 2:
        return []

    # ------------------------------------------------------------------ #
    # 3.  Build per-account monthly balance with carry-forward
    # ------------------------------------------------------------------ #
    current_balance: dict = {acct: 0.0 for acct in all_accounts}
    monthly_balances: list[dict] = []  # list of {account_id: balance}

    for month in all_months:
        for acct in all_accounts:
            entry = last_per_acct_month.get((acct, month))
            if entry is not None:
                current_balance[acct] = entry[1]
        monthly_balances.append(dict(current_balance))

    # ------------------------------------------------------------------ #
    # 4.  Compute deltas grouped by display_group
    # ------------------------------------------------------------------ #
    results: list[dict] = []

    for i in range(1, len(all_months)):
        prev_bal = monthly_balances[i - 1]
        curr_bal = monthly_balances[i]

        group_deltas: dict[str, float] = defaultdict(float)
        for acct in all_accounts:
            delta = curr_bal[acct] - prev_bal[acct]
            grp = account_group[acct]
            group_deltas[grp] += delta

        row: dict = {"month": all_months[i]}
        total = 0.0
        for grp in all_groups:
            val = round(group_deltas.get(grp, 0.0), 2)
            row[grp] = val
            total += val
        row["total"] = round(total, 2)

        results.append(row)

    return results
