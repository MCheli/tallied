"""Balance snapshots: the one source of truth for account balances (PRODUCT.md "One source of truth").

- `latest_balances(db)` returns the newest snapshot per active account, deduplicated
  when two sources wrote the same account on the same day (the (account, date, source)
  uniqueness allowed that; the old max-date join summed both rows).
- `record_balance(db, ...)` is how other pages (Property valuation, 401(k) statement
  import) push their figure into net worth and Planning instead of keeping a
  parallel number (decision D2).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.balance import BalanceSnapshot


@dataclass
class LatestBalance:
    account_id: str
    name: str
    display_group: str
    account_type: str
    include_in_nw: bool
    balance: float
    as_of: date


def latest_balances(db: Session, *, on_or_before: date | None = None) -> list[LatestBalance]:
    """Newest snapshot per active account (optionally as of a past date); one row per account."""
    date_filter = [BalanceSnapshot.snapshot_date <= on_or_before] if on_or_before else []
    latest_sub = (
        select(BalanceSnapshot.account_id, func.max(BalanceSnapshot.snapshot_date).label("max_date"))
        .where(*date_filter)
        .group_by(BalanceSnapshot.account_id)
        .subquery()
    )
    stmt = (
        select(
            Account.id, Account.name, Account.display_group, Account.account_type, Account.include_in_nw,
            BalanceSnapshot.id, BalanceSnapshot.balance, BalanceSnapshot.snapshot_date,
        )
        .join(latest_sub, Account.id == latest_sub.c.account_id)
        .join(
            BalanceSnapshot,
            (BalanceSnapshot.account_id == Account.id) & (BalanceSnapshot.snapshot_date == latest_sub.c.max_date),
        )
        .where(Account.is_active.is_(True))
        .order_by(Account.id, BalanceSnapshot.id.desc())
    )
    out: dict[str, LatestBalance] = {}
    for acct_id, name, group, acct_type, include_nw, _snap_id, balance, snap_date in db.execute(stmt).all():
        if acct_id in out:
            continue  # a later-inserted row for the same day already won
        out[acct_id] = LatestBalance(
            account_id=acct_id, name=name, display_group=group or "", account_type=acct_type,
            include_in_nw=bool(include_nw), balance=float(balance) if balance is not None else 0.0,
            as_of=snap_date,
        )
    return list(out.values())


def normalize_group(display_group: str) -> str:
    return (display_group or "").lower().replace(" ", "_")


def record_balance(db: Session, account_id: str, value: Decimal | float, snapshot_date: date, source: str) -> BalanceSnapshot:
    """Upsert the (account, date, source) snapshot. Does not commit."""
    value = Decimal(str(value))
    existing = db.execute(
        select(BalanceSnapshot).where(
            BalanceSnapshot.account_id == account_id,
            BalanceSnapshot.snapshot_date == snapshot_date,
            BalanceSnapshot.source == source,
        )
    ).scalar_one_or_none()
    if existing:
        existing.balance = value
        return existing
    snap = BalanceSnapshot(account_id=account_id, snapshot_date=snapshot_date, balance=value, source=source)
    db.add(snap)
    return snap
