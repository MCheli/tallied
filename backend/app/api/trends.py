from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import year_month
from app.dependencies import get_tenant_db
from app.models.account import Account
from app.models.balance import BalanceSnapshot

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/net-worth")
def net_worth_trend(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_tenant_db),
):
    """Net worth by display_group over time."""
    from app.services.balances import normalize_group
    from app.services.snapshot_service import LAYER_NAMES

    stmt = (
        select(
            BalanceSnapshot.snapshot_date,
            BalanceSnapshot.account_id,
            BalanceSnapshot.id,
            Account.display_group,
            BalanceSnapshot.balance,
        )
        .join(Account, BalanceSnapshot.account_id == Account.id)
        .where(Account.include_in_nw.is_(True))
        .where(Account.is_active.is_(True))
        .order_by(BalanceSnapshot.snapshot_date, BalanceSnapshot.account_id, BalanceSnapshot.id)
    )

    if from_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date >= from_date)
    if to_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date <= to_date)

    rows = db.execute(stmt).all()

    # One balance per (account, date): the newest row wins when two sources wrote the same day.
    per_day: dict[tuple[str, str], tuple[str, float]] = {}
    for snap_date, acct_id, _snap_id, group, balance in rows:
        key = normalize_group(group)
        per_day[(snap_date.isoformat(), acct_id)] = (LAYER_NAMES.get(key, key.replace("_", " ").title()),
                                                     float(balance) if balance else 0.0)

    # Each account counts at its last known balance on every later day (carry-forward):
    # a house valued in April or a 401(k) statement from September is still worth that
    # until the next figure, not zero on the days nothing new was written.
    by_account: dict[str, dict[str, tuple[str, float]]] = {}
    for (d, acct), (group, val) in per_day.items():
        by_account.setdefault(acct, {})[d] = (group, val)
    all_dates = sorted({d for (d, _acct) in per_day})
    if not all_dates:
        return {"dates": [], "groups": {}, "totals": []}

    # Start where the picture is complete: the latest first-balance date among accounts
    # that already existed 90 days before the last date. Earlier days would show, say,
    # the mortgage without the house. Accounts opened in the last 90 days count from
    # their first balance and do not cut the history short.
    last = date.fromisoformat(all_dates[-1])
    firsts = {acct: min(days) for acct, days in by_account.items()}
    established = [f for f in firsts.values() if (last - date.fromisoformat(f)).days >= 90]
    start = max(established) if established else all_dates[0]
    if from_date is None:
        dates = [d for d in all_dates if d >= start]
    else:
        dates = all_dates

    all_groups = sorted({g for days in by_account.values() for (g, _v) in days.values()})
    groups: dict[str, list[float]] = {g: [] for g in all_groups}
    totals: list[float] = []
    current: dict[str, tuple[str, float]] = {}
    pending = iter(all_dates)
    nxt = next(pending, None)
    for d in dates:
        while nxt is not None and nxt <= d:
            for acct, days in by_account.items():
                if nxt in days:
                    current[acct] = days[nxt]
            nxt = next(pending, None)
        day = dict.fromkeys(all_groups, 0.0)
        for group, val in current.values():
            day[group] += val
        for g in all_groups:
            groups[g].append(round(day[g], 2))
        totals.append(round(sum(day.values()), 2))

    return {"dates": dates, "groups": groups, "totals": totals}


@router.get("/balances")
def balance_trend(
    account_ids: str | None = Query(None, description="Comma-separated account IDs"),
    display_group: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_tenant_db),
):
    """Balance history for selected accounts or groups."""
    stmt = (
        select(
            BalanceSnapshot.snapshot_date,
            Account.id,
            Account.name,
            BalanceSnapshot.balance,
        )
        .join(Account, BalanceSnapshot.account_id == Account.id)
        .order_by(BalanceSnapshot.snapshot_date)
    )

    if account_ids:
        ids = [aid.strip() for aid in account_ids.split(",")]
        stmt = stmt.where(Account.id.in_(ids))
    if display_group:
        stmt = stmt.where(Account.display_group == display_group)
    if from_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date >= from_date)
    if to_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date <= to_date)

    rows = db.execute(stmt).all()

    # Group by account
    series: dict[str, dict] = {}
    for snap_date, acct_id, acct_name, balance in rows:
        if acct_id not in series:
            series[acct_id] = {"name": acct_name, "dates": [], "balances": []}
        series[acct_id]["dates"].append(snap_date.isoformat())
        series[acct_id]["balances"].append(float(balance) if balance else 0.0)

    return {"accounts": list(series.values())}


@router.get("/cash-flow")
def cash_flow(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_tenant_db),
):
    """Monthly balance changes by account type."""
    stmt = (
        select(
            year_month(BalanceSnapshot.snapshot_date).label("month"),
            Account.account_type,
            func.sum(BalanceSnapshot.balance).label("total"),
        )
        .join(Account, BalanceSnapshot.account_id == Account.id)
        .where(Account.is_active.is_(True))
        .group_by("month", Account.account_type)
        .order_by("month")
    )

    if from_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date >= from_date)
    if to_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date <= to_date)

    rows = db.execute(stmt).all()

    # Structure: list of {month, types: {type: total}}
    months_data: dict[str, dict[str, float]] = {}
    for month, acct_type, total in rows:
        if month not in months_data:
            months_data[month] = {}
        months_data[month][acct_type] = float(total) if total else 0.0

    result = []
    sorted_months = sorted(months_data.keys())
    prev: dict[str, float] = {}
    for month in sorted_months:
        current = months_data[month]
        changes: dict[str, float] = {}
        all_types = set(current.keys()) | set(prev.keys())
        for t in all_types:
            changes[t] = round(current.get(t, 0.0) - prev.get(t, 0.0), 2)
        result.append({"month": month, "changes": changes})
        prev = current

    return {"months": result}
