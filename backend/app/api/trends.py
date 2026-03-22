from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.balance import BalanceSnapshot

router = APIRouter(prefix="/api/trends", tags=["trends"])


@router.get("/net-worth")
def net_worth_trend(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    """Net worth by display_group over time."""
    stmt = (
        select(
            BalanceSnapshot.snapshot_date,
            Account.display_group,
            func.sum(BalanceSnapshot.balance).label("total"),
        )
        .join(Account, BalanceSnapshot.account_id == Account.id)
        .where(Account.include_in_nw.is_(True))
        .where(Account.is_active.is_(True))
        .group_by(BalanceSnapshot.snapshot_date, Account.display_group)
        .order_by(BalanceSnapshot.snapshot_date)
    )

    if from_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date >= from_date)
    if to_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date <= to_date)

    rows = db.execute(stmt).all()

    # Build series: {date_str: {group: total}}
    date_groups: dict[str, dict[str, float]] = {}
    all_groups: set[str] = set()

    for snap_date, group, total in rows:
        d = snap_date.isoformat()
        if d not in date_groups:
            date_groups[d] = {}
        date_groups[d][group] = float(total) if total else 0.0
        all_groups.add(group)

    dates = sorted(date_groups.keys())
    groups: dict[str, list[float]] = {g: [] for g in sorted(all_groups)}
    totals: list[float] = []

    for d in dates:
        day_total = 0.0
        for g in sorted(all_groups):
            val = date_groups[d].get(g, 0.0)
            groups[g].append(val)
            day_total += val
        totals.append(day_total)

    return {"dates": dates, "groups": groups, "totals": totals}


@router.get("/balances")
def balance_trend(
    account_ids: str | None = Query(None, description="Comma-separated account IDs"),
    display_group: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
):
    """Monthly balance changes by account type."""
    stmt = (
        select(
            func.strftime("%Y-%m", BalanceSnapshot.snapshot_date).label("month"),
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
