"""Vested company shares as a net worth account (Dashboard layer "Company Stock").

Shares the owner can sell today are money they have. Each day the scheduler writes one balance
snapshot to a system account: sellable shares x that day's close. Unvested shares are not
counted (they are not owned yet). The first time it runs, it backfills weekly closes back to the
start of the household's balance history, assuming the shares held on a past day were today's
sellable shares less what vested since (no sales in between); the tooltip says so.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.investment import RSUGrant, VestEvent

logger = logging.getLogger("tallied.company_stock")

ACCOUNT_ID = "company-stock"
SOURCE = "company_stock"


def sellable_shares(db: Session) -> tuple[str | None, int]:
    grants = db.execute(select(RSUGrant)).scalars().all()
    symbol = next((g.symbol for g in grants if g.symbol), None)
    return symbol, sum(g.sellable_shares or 0 for g in grants)


def shares_held_on(db: Session, day: date, today: date, sellable_now: int) -> int:
    """Today's sellable shares less the net shares released by vests after `day` (no sales assumed)."""
    released_since = db.execute(
        select(func.coalesce(func.sum(func.coalesce(
            VestEvent.shares_released, VestEvent.shares - func.coalesce(VestEvent.shares_withheld, 0))), 0))
        .where(VestEvent.is_actual.is_(True), VestEvent.vest_date > day, VestEvent.vest_date <= today)
    ).scalar()
    return max(0, sellable_now - int(released_since or 0))


def _account(db: Session, symbol: str) -> Account:
    acct = db.get(Account, ACCOUNT_ID)
    if acct is None:
        acct = Account(id=ACCOUNT_ID, name=f"{symbol} shares (vested)", institution="Company stock plan",
                       account_type="investment_stock", display_group="Company Stock", include_in_nw=True)
        db.add(acct)
        db.flush()
    return acct


def record_values(db: Session, prices: list[tuple[date, float]], today: date) -> int:
    """Write (or overwrite) the company stock balance for each priced day. Does not commit. Returns rows written."""
    symbol, sellable_now = sellable_shares(db)
    if not symbol:
        return 0
    _account(db, symbol)
    written = 0
    for day, price in prices:
        if day > today or price is None:
            continue
        value = Decimal(str(round(shares_held_on(db, day, today, sellable_now) * price, 2)))
        row = db.execute(select(BalanceSnapshot).where(
            BalanceSnapshot.account_id == ACCOUNT_ID, BalanceSnapshot.snapshot_date == day,
            BalanceSnapshot.source == SOURCE)).scalar_one_or_none()
        if row:
            row.balance = value
        else:
            db.add(BalanceSnapshot(account_id=ACCOUNT_ID, snapshot_date=day, balance=value, source=SOURCE))
        written += 1
    db.flush()
    return written


def refresh(db: Session, today: date | None = None) -> int:
    """Today's value, plus a weekly backfill the first time. Commits. Returns rows written."""
    from app.services.stock_price import fetch_price_history, get_or_fetch_price

    today = today or date.today()
    symbol, _ = sellable_shares(db)
    if not symbol:
        return 0
    prices: list[tuple[date, float]] = []
    has_history = db.execute(select(func.count()).select_from(BalanceSnapshot)
                             .where(BalanceSnapshot.account_id == ACCOUNT_ID)).scalar()
    if not has_history:
        start = db.execute(select(func.min(BalanceSnapshot.snapshot_date))
                           .where(BalanceSnapshot.account_id != ACCOUNT_ID)).scalar() or today
        try:
            prices += [(date.fromisoformat(p["date"]), p["price"]) for p in fetch_price_history(symbol, "2y")
                       if date.fromisoformat(p["date"]) >= start]
        except ValueError as e:
            logger.warning("Company stock backfill skipped: %s", e)
    price = get_or_fetch_price(db, symbol)
    if price is not None:
        prices.append((today, price))
    written = record_values(db, prices, today)
    db.commit()
    return written
