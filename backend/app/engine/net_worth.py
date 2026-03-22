"""
Net worth computation from balance snapshots.

Pure computation, no framework dependencies.
"""

from __future__ import annotations

from collections import defaultdict


def _month_key(date_str: str) -> str:
    """Extract 'YYYY-MM' from an ISO-ish date string."""
    return date_str[:7]


def compute_net_worth_series(snapshots: list[dict]) -> dict:
    """
    Takes balance snapshots grouped by account / display_group over time.
    Returns monthly net worth by group.

    Parameters
    ----------
    snapshots : list[dict]
        Each dict must contain:
          - account_id : str | int
          - display_group : str   (e.g. "Cash", "Investments", "Home Equity", …)
          - snapshot_date : str   (ISO date, e.g. "2025-03-15")
          - balance : float

    Returns
    -------
    dict
        {
            "dates": ["2025-01", "2025-02", ...],
            "groups": {
                "Cash": [10000, 10500, ...],
                "Investments": [200000, 205000, ...],
                ...
            },
            "totals": [500000, 510000, ...]
        }

    Notes
    -----
    - Uses the *last* balance per account per month (latest snapshot_date wins).
    - Months are sorted chronologically.
    - If an account has no snapshot in a given month, its balance is carried
      forward from the most recent prior month.
    """
    if not snapshots:
        return {"dates": [], "groups": {}, "totals": []}

    # ------------------------------------------------------------------ #
    # 1.  Find last balance per (account, month)
    # ------------------------------------------------------------------ #
    # Key: (account_id, month) -> (snapshot_date, balance)
    last_per_account_month: dict[tuple, tuple[str, float]] = {}

    for s in snapshots:
        acct = s["account_id"]
        month = _month_key(s["snapshot_date"])
        date = s["snapshot_date"]
        balance = s["balance"]
        key = (acct, month)
        prev = last_per_account_month.get(key)
        if prev is None or date > prev[0]:
            last_per_account_month[key] = (date, balance)

    # ------------------------------------------------------------------ #
    # 2.  Build unique sorted month list and account metadata
    # ------------------------------------------------------------------ #
    all_months: set[str] = set()
    account_group: dict = {}  # account_id -> display_group

    for s in snapshots:
        all_months.add(_month_key(s["snapshot_date"]))
        account_group[s["account_id"]] = s["display_group"]

    sorted_months = sorted(all_months)
    all_accounts = sorted(account_group.keys(), key=str)

    # ------------------------------------------------------------------ #
    # 3.  For each month, resolve balance per account (carry-forward)
    # ------------------------------------------------------------------ #
    # current_balance[account_id] -> latest known balance
    current_balance: dict = {acct: 0.0 for acct in all_accounts}

    # group -> [balance_per_month]
    group_series: dict[str, list[float]] = defaultdict(list)
    totals: list[float] = []

    all_groups = sorted(set(account_group.values()))

    for month in sorted_months:
        # Update balances for accounts that have a snapshot this month
        for acct in all_accounts:
            entry = last_per_account_month.get((acct, month))
            if entry is not None:
                current_balance[acct] = entry[1]

        # Sum by group
        group_sums: dict[str, float] = defaultdict(float)
        for acct in all_accounts:
            grp = account_group[acct]
            group_sums[grp] += current_balance[acct]

        total = 0.0
        for grp in all_groups:
            val = round(group_sums.get(grp, 0.0), 2)
            group_series[grp].append(val)
            total += val
        totals.append(round(total, 2))

    return {
        "dates": sorted_months,
        "groups": {g: group_series[g] for g in all_groups},
        "totals": totals,
    }
