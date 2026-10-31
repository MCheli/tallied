"""Vested company shares as a net worth account (Dashboard layer "Company Stock").

Shares the owner can sell today are money they have. Each day the scheduler writes one balance
snapshot to a system account: sellable shares x that day's close. Unvested shares are not
counted (they are not owned yet). The first time it runs, it backfills weekly closes back to the
start of the household's balance history.

Past holdings are estimated per grant, because sale dates are not recorded: each grant is assumed
to have kept the same share of every release that it holds today (sellable / released). A grant
never sold from gives "today's shares less what vested since"; a grant sold down to nothing counts
as zero throughout; the estimate always lands exactly on today's sellable shares.
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


def holdings(db: Session, today: date):
    """A function day -> estimated shares held at the end of that day (see the module docstring)."""
    grants = db.execute(select(RSUGrant)).scalars().all()
    rows = db.execute(
        select(VestEvent.grant_id, VestEvent.vest_date,
               func.coalesce(VestEvent.shares_released, VestEvent.shares - func.coalesce(VestEvent.shares_withheld, 0)))
        .where(VestEvent.is_actual.is_(True), VestEvent.vest_date <= today)
    ).all()
    releases: dict[str, list[tuple[date, float]]] = {}
    for grant_id, day, released in rows:
        releases.setdefault(grant_id, []).append((day, float(released or 0)))

    plans = []  # (keep share of each release, shares held outside any recorded release, releases)
    for g in grants:
        sellable = float(g.sellable_shares or 0)
        rel = releases.get(g.id, [])
        total = sum(n for _, n in rel)
        if total <= 0:
            plans.append((0.0, sellable, []))
        else:
            plans.append((min(1.0, sellable / total), max(0.0, sellable - total), rel))

    def held_on(day: date) -> float:
        return sum(extra + keep * sum(n for d, n in rel if d <= day) for keep, extra, rel in plans)

    return held_on


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
    symbol, _ = sellable_shares(db)
    if not symbol:
        return 0
    _account(db, symbol)
    held_on = holdings(db, today)
    written = 0
    for day, price in prices:
        if day > today or price is None:
            continue
        value = Decimal(str(round(held_on(day) * price, 2)))
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


def refresh(db: Session, today: date | None = None, rebuild: bool = False) -> int:
    """Today's value, plus a weekly backfill the first time (or every time with rebuild=True, which first
    deletes the history this module wrote). Commits. Returns rows written."""
    from app.services.stock_price import get_or_fetch_price, price_series

    today = today or date.today()
    symbol, _ = sellable_shares(db)
    if not symbol:
        return 0
    if rebuild:
        db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == ACCOUNT_ID,
                                         BalanceSnapshot.source == SOURCE).delete()
        db.flush()
    prices: list[tuple[date, float]] = []
    has_history = db.execute(select(func.count()).select_from(BalanceSnapshot)
                             .where(BalanceSnapshot.account_id == ACCOUNT_ID)).scalar()
    if not has_history:
        start = db.execute(select(func.min(BalanceSnapshot.snapshot_date))
                           .where(BalanceSnapshot.account_id != ACCOUNT_ID)).scalar() or today
        try:
            prices += [(date.fromisoformat(p["date"]), p["price"]) for p in price_series(db, symbol, "2y", today)
                       if date.fromisoformat(p["date"]) >= start]
        except ValueError as e:
            logger.warning("Company stock backfill skipped: %s", e)
    price = get_or_fetch_price(db, symbol)
    if price is not None:
        prices.append((today, price))
    written = record_values(db, prices, today)
    db.commit()
    return written
