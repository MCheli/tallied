"""Balance snapshots: the one source of truth for account balances (PRODUCT.md "One source of truth").

- `latest_balances(db)` returns the newest snapshot per active account, deduplicated
  when two sources wrote the same account on the same day (the (account, date, source)
  uniqueness allowed that; the old max-date join summed both rows).
- `record_balance(db, ...)` is how other pages (Property valuation, 401(k) statement
  import) push their figure into net worth and Planning instead of keeping a
  parallel number (decision D2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.property import PropertyValuation
from app.models.retirement import RetirementAccount

logger = logging.getLogger("tallied.balances")


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


def ensure_retirement_account(db: Session, ret_acct: RetirementAccount) -> Account:
    """The `accounts` row that carries this 401(k)'s balance into net worth; created if missing.

    A 401(k) statement import used to skip the balance silently when no investment_401k
    account existed, which left the 401(k) out of net worth entirely. Does not commit.
    """
    if ret_acct.account_id:
        linked = db.get(Account, ret_acct.account_id)
        if linked is not None:
            return linked
    account = db.execute(
        select(Account).where(Account.account_type == "investment_401k").order_by(Account.id).limit(1)
    ).scalar_one_or_none()
    if account is None:
        account = Account(
            id=f"retirement-{ret_acct.id}",
            name=ret_acct.plan_name or "401(k)",
            institution=ret_acct.provider,
            account_type="investment_401k",
            display_group="Retirement",
            include_in_nw=True,
            is_active=True,
        )
        db.add(account)
        db.flush()
        logger.info("Created 401(k) account %s for retirement account %s", account.id, ret_acct.id)
    ret_acct.account_id = account.id
    return account


def _has_snapshot_on_or_after(db: Session, account_id: str, on: date) -> bool:
    return db.execute(
        select(BalanceSnapshot.id).where(
            BalanceSnapshot.account_id == account_id, BalanceSnapshot.snapshot_date >= on
        ).limit(1)
    ).first() is not None


def backfill_asset_balances(db: Session) -> dict[str, int]:
    """Write the balance snapshots D2 expects but older data never got. Idempotent; does not commit.

    - Each real-estate account gets its latest valuation as a balance, unless a balance
      dated on or after that valuation already exists.
    - Each 401(k) with a statement balance gets an account (if missing) and that balance,
      dated at the statement end, under the same condition.
    """
    counts = {"property": 0, "retirement": 0}
    for account in db.execute(select(Account).where(Account.account_type == "real_estate")).scalars():
        latest = db.execute(
            select(PropertyValuation)
            .where(PropertyValuation.account_id == account.id)
            .order_by(PropertyValuation.valuation_date.desc(), PropertyValuation.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None or latest.value is None:
            continue
        if _has_snapshot_on_or_after(db, account.id, latest.valuation_date):
            continue
        record_balance(db, account.id, latest.value, latest.valuation_date, "valuation")
        counts["property"] += 1
    for ret_acct in db.execute(select(RetirementAccount)).scalars():
        if ret_acct.total_balance is None:
            continue
        account = ensure_retirement_account(db, ret_acct)
        as_of = ret_acct.statement_end or date.today()
        if _has_snapshot_on_or_after(db, account.id, as_of):
            continue
        record_balance(db, account.id, ret_acct.total_balance, as_of, "statement")
        counts["retirement"] += 1
    db.flush()
    return counts
