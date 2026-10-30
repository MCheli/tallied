"""Month-to-date spending pace and the weekly recap (Dashboard and the Recap page). Read-only.

Both use the one definition of spending (services.spending_rules.spending_filter): money out net of
refunds, transfers and loan/card payments excluded. Amounts are returned as positive "spent" figures.

The recap is computed from the data each time it is asked for, so every past week has one without a
job writing anything: a week is Sunday to Saturday, and the default is the last completed week.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine.spending import detect_recurring
from app.models.investment import RSUGrant, StockPrice, VestEvent
from app.models.transaction import Transaction
from app.services.balances import latest_balances
from app.services.spending_rules import INCOME_CATEGORIES, spending_filter

PRIOR_WEEKS = 4
VEST_LOOKAHEAD_DAYS = 30


def _month_start(d: date, offset: int = 0) -> date:
    m = d.month - 1 + offset
    return date(d.year + m // 12, m % 12 + 1, 1)


def _daily_spending(db: Session, start: date, end: date) -> dict[date, float]:
    rows = db.execute(
        spending_filter(select(Transaction.date, func.sum(Transaction.amount)))
        .where(Transaction.date >= start, Transaction.date <= end)
        .group_by(Transaction.date)
    ).all()
    return {d: -float(total or 0) for d, total in rows}


def cumulative(daily: dict[date, float], start: date, days: int) -> list[float]:
    """Running total of spending for each day of a month, starting on day 1."""
    out, running = [], 0.0
    for i in range(days):
        running += daily.get(start + timedelta(days=i), 0.0)
        out.append(round(running, 2))
    return out


def month_pace(db: Session, today: date, month: date | None = None) -> dict:
    """Cumulative spending by day of month for a month and the month before it.

    The current month stops at today; a past month runs to its last day. ``same_day_last_month`` is
    last month's running total on the same day number (its last day when it was shorter).
    """
    this_start = _month_start(month or today)
    last_start = _month_start(this_start, -1)
    this_days = calendar.monthrange(this_start.year, this_start.month)[1]
    last_days = calendar.monthrange(last_start.year, last_start.month)[1]
    elapsed = this_days if today >= _month_start(this_start, 1) else max(0, (today - this_start).days + 1)

    daily = _daily_spending(db, last_start, this_start + timedelta(days=this_days - 1))
    this_series = cumulative(daily, this_start, elapsed)
    last_series = cumulative(daily, last_start, last_days)
    day = len(this_series)
    return {
        "month": this_start.strftime("%Y-%m"),
        "last_month": last_start.strftime("%Y-%m"),
        "days_in_month": max(this_days, last_days),
        "this_month": this_series,
        "last_month_series": last_series,
        "this_total": this_series[-1] if this_series else 0.0,
        "same_day_last_month": last_series[min(day, last_days) - 1] if day else 0.0,
        "last_month_total": last_series[-1] if last_series else 0.0,
    }


def last_completed_week(today: date) -> date:
    """Sunday that starts the most recent Sunday–Saturday week ending before today."""
    days_since_saturday = (today.weekday() - 5) % 7 or 7
    return today - timedelta(days=days_since_saturday + 6)


def _net_worth(db: Session, on: date) -> float | None:
    rows = [b for b in latest_balances(db, on_or_before=on) if b.include_in_nw]
    return round(sum(b.balance for b in rows), 2) if rows else None


def _spending_rows(db: Session, start: date, end: date):
    return db.execute(
        spending_filter(select(Transaction.date, Transaction.amount, Transaction.merchant, Transaction.category))
        .where(Transaction.date >= start, Transaction.date <= end)
    ).all()


def _next_charge(last: date) -> date:
    """A monthly bill's next date: the same day next month (clamped to the month's end)."""
    nxt = _month_start(last, 1)
    return nxt.replace(day=min(last.day, calendar.monthrange(nxt.year, nxt.month)[1]))


def weekly_recap(db: Session, today: date, week_start: date | None = None) -> dict:
    start = week_start or last_completed_week(today)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # any date → its Sunday
    end = start + timedelta(days=6)
    prior_start = start - timedelta(days=7 * PRIOR_WEEKS)

    week_rows = _spending_rows(db, start, end)
    prior_rows = _spending_rows(db, prior_start, start - timedelta(days=1))
    spent = -sum(float(r.amount) for r in week_rows)
    prior_avg = -sum(float(r.amount) for r in prior_rows) / PRIOR_WEEKS

    by_cat: dict[str, float] = defaultdict(float)
    prior_cat: dict[str, float] = defaultdict(float)
    for r in week_rows:
        by_cat[r.category or "Uncategorized"] -= float(r.amount)
    for r in prior_rows:
        prior_cat[r.category or "Uncategorized"] -= float(r.amount) / PRIOR_WEEKS
    categories = sorted(
        ({"category": c, "total": round(v, 2), "prior_avg": round(prior_cat.get(c, 0.0), 2)} for c, v in by_cat.items() if v > 0.005),
        key=lambda c: -c["total"],
    )[:6]
    largest = sorted((r for r in week_rows if r.amount < 0), key=lambda r: r.amount)[:5]

    income_rows = db.execute(
        select(Transaction.amount).where(
            Transaction.date >= start, Transaction.date <= end, Transaction.amount > 0,
            func.lower(Transaction.category).in_(INCOME_CATEGORIES),
        )
    ).all()

    nw_start, nw_end = _net_worth(db, start - timedelta(days=1)), _net_worth(db, end)

    # Coming up: bills due the week after by their monthly pattern, and RSU vests in the next 30 days.
    next_start, next_end = end + timedelta(days=1), end + timedelta(days=7)
    history = [
        {"date": r.date.isoformat(), "amount": float(r.amount), "merchant": r.merchant, "category": r.category}
        for r in _spending_rows(db, end - timedelta(days=180), end) if r.merchant
    ]
    bills = []
    for b in detect_recurring(history, end.isoformat()):
        due = _next_charge(date.fromisoformat(b["last_date"]))
        if next_start <= due <= next_end:
            bills.append({"merchant": b["merchant"], "category": b["category"], "date": due.isoformat(), "amount": abs(b["avg_monthly"])})
    bills.sort(key=lambda b: b["date"])

    price_sub = (
        select(StockPrice.symbol, func.max(StockPrice.price_date).label("d")).group_by(StockPrice.symbol).subquery()
    )
    prices = {
        s: float(p) for s, p in db.execute(
            select(StockPrice.symbol, StockPrice.close_price)
            .join(price_sub, (StockPrice.symbol == price_sub.c.symbol) & (StockPrice.price_date == price_sub.c.d))
        ).all()
    }
    vests: dict[date, dict] = {}
    for vest_date, shares, symbol in db.execute(
        select(VestEvent.vest_date, VestEvent.shares, RSUGrant.symbol)
        .join(RSUGrant, VestEvent.grant_id == RSUGrant.id)
        .where(VestEvent.vest_date >= next_start, VestEvent.vest_date <= end + timedelta(days=VEST_LOOKAHEAD_DAYS),
               VestEvent.is_actual.is_(False))
    ).all():
        row = vests.setdefault(vest_date, {"date": vest_date.isoformat(), "shares": 0, "est_value": 0.0})
        row["shares"] += shares
        row["est_value"] = round(row["est_value"] + shares * prices.get(symbol or "", 0.0), 2)

    recap = {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "complete": end < today,
        "previous_week": (start - timedelta(days=7)).isoformat(),
        "next_week": next_start.isoformat() if next_start <= last_completed_week(today) else None,
        "net_worth_start": nw_start,
        "net_worth_end": nw_end,
        "net_worth_change": round(nw_end - nw_start, 2) if nw_start is not None and nw_end is not None else None,
        "spending": round(spent, 2),
        "prior_weekly_avg": round(prior_avg, 2),
        "transaction_count": sum(1 for r in week_rows if r.amount < 0),
        "income": round(sum(float(r.amount) for r in income_rows), 2),
        "categories": categories,
        "largest": [
            {"date": r.date.isoformat(), "merchant": r.merchant or "Unknown", "category": r.category or "Uncategorized", "amount": round(-float(r.amount), 2)}
            for r in largest
        ],
        "uncategorized": sum(1 for r in week_rows if not r.category),
        "upcoming_bills": bills,
        "upcoming_vests": sorted(vests.values(), key=lambda v: v["date"]),
    }
    recap["headline"] = headline(recap)
    return recap


def usd(v: float) -> str:
    return f"${abs(v):,.0f}"


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def headline(r: dict) -> str:
    """One plain sentence from the recap's numbers; no model writes it, so it is never a guess."""
    parts: list[str] = []
    if r["spending"] <= 0:
        parts.append("No spending this week")
    else:
        s = f"You spent {usd(r['spending'])}"
        avg = r["prior_weekly_avg"]
        if avg > 0:
            pct = round((r["spending"] - avg) / avg * 100)
            s += ", about your usual week" if abs(pct) < 5 else f", {abs(pct)}% {'more' if pct > 0 else 'less'} than your 4-week average of {usd(avg)}"
        if r["categories"]:
            top = r["categories"][0]
            s += f"; the most went to {top['category']} ({usd(top['total'])})"
        parts.append(s)
    change = r["net_worth_change"]
    if change is not None:
        parts.append("Net worth held steady" if change == 0 else f"Net worth {'rose' if change > 0 else 'fell'} {usd(change)}")
    if r["upcoming_bills"]:
        n = len(r["upcoming_bills"])
        parts.append(f"Next week: {n} bill{'s' if n > 1 else ''} (~{usd(sum(b['amount'] for b in r['upcoming_bills']))})")
    vests = r["upcoming_vests"]
    if vests:
        shares, value = sum(v["shares"] for v in vests), sum(v["est_value"] for v in vests)
        when = ", ".join(short_date(v["date"]) for v in vests)
        parts.append(f"RSU vest{'s' if len(vests) > 1 else ''} {when}: {shares} shares (~{usd(value)})")
    return ". ".join(parts) + "."

