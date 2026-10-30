from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import year_month
from app.dependencies import get_tenant_db
from app.engine.spending import detect_recurring
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.transaction import CategorySummary, MonthlySpending, RecurringExpense
from app.services.spending_rules import EXCLUDED_CATEGORIES, spending_filter

router = APIRouter(prefix="/spending", tags=["spending"])


def _parse_account_types(raw: str | None) -> list[str] | None:
    """Comma-separated account_types → list, or None for no filter."""
    if not raw:
        return None
    types = [t.strip() for t in raw.split(",") if t.strip()]
    return types or None


def _apply_account_type_filter(stmt, account_types: list[str] | None):
    """Restrict a Transaction-based query to txns whose account is one of
    the given account_types. NULL account_id rows (e.g. email receipts)
    are excluded when a filter is active."""
    if not account_types:
        return stmt
    return stmt.where(
        Transaction.account_id.in_(
            select(Account.id).where(Account.account_type.in_(account_types))
        )
    )


@router.get("/by-category", response_model=list[CategorySummary])
def spending_by_category(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    account_types: str | None = Query(None, description="Comma-separated account_types to include"),
    db: Session = Depends(get_tenant_db),
):
    """Category totals for a date range (spending only: negative amounts, transfers and loan payments excluded)."""
    stmt = spending_filter(
        select(
            Transaction.category,
            Transaction.category_group,
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
    ).group_by(Transaction.category, Transaction.category_group).order_by(func.sum(Transaction.amount))

    if from_date:
        stmt = stmt.where(Transaction.date >= from_date)
    if to_date:
        stmt = stmt.where(Transaction.date <= to_date)
    stmt = _apply_account_type_filter(stmt, _parse_account_types(account_types))

    rows = db.execute(stmt).all()

    grand_total = sum(abs(float(r.total)) for r in rows) if rows else 1.0

    return [
        CategorySummary(
            category=r.category or "Uncategorized",
            category_group=r.category_group,
            total=round(float(r.total), 2),
            count=r.count,
            pct_of_total=round(abs(float(r.total)) / grand_total * 100, 1),
        )
        for r in rows
    ]


@router.get("/recurring", response_model=list[RecurringExpense])
def recurring_expenses(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    months: int = Query(6, ge=1, le=24, description="Lookback months when no date range is given"),
    account_types: str | None = Query(None, description="Comma-separated account_types to include"),
    db: Session = Depends(get_tenant_db),
):
    """Bills and subscriptions in the period: charged about monthly at a steady amount and still active
    (engine.spending.detect_recurring). avg_monthly is what the bill costs a month."""
    from datetime import timedelta

    end = to_date or date.today()
    start = from_date or (end - timedelta(days=months * 30))
    months_in_range = max(1, (end.year - start.year) * 12 + (end.month - start.month) + 1)

    stmt = spending_filter(
        select(Transaction.date, Transaction.amount, Transaction.merchant, Transaction.category)
    ).where(Transaction.date >= start, Transaction.date <= end, Transaction.merchant.isnot(None))
    stmt = _apply_account_type_filter(stmt, _parse_account_types(account_types))
    rows = [
        {"date": r.date.isoformat(), "amount": float(r.amount), "merchant": r.merchant, "category": r.category}
        for r in db.execute(stmt).all()
    ]
    found = detect_recurring(rows, end.isoformat(), min_months=2 if months_in_range <= 4 else 3)
    return [
        RecurringExpense(
            merchant=r["merchant"], category=r["category"], avg_monthly=abs(r["avg_monthly"]),
            months_seen=r["months_seen"], last_date=date.fromisoformat(r["last_date"]),
        )
        for r in found
    ]


@router.get("/excluded-categories")
def excluded_categories():
    """Categories that never count as spending (transfers and loan/card payments)."""
    return sorted(EXCLUDED_CATEGORIES)


@router.get("/monthly-trend", response_model=list[MonthlySpending])
def monthly_spending_trend(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    account_types: str | None = Query(None, description="Comma-separated account_types to include"),
    db: Session = Depends(get_tenant_db),
):
    """Monthly spending totals (same definition as by-category)."""
    stmt = spending_filter(
        select(
            year_month(Transaction.date).label("month"),
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
    ).group_by("month").order_by("month")

    if from_date:
        stmt = stmt.where(Transaction.date >= from_date)
    if to_date:
        stmt = stmt.where(Transaction.date <= to_date)
    stmt = _apply_account_type_filter(stmt, _parse_account_types(account_types))

    rows = db.execute(stmt).all()

    return [
        MonthlySpending(
            month=r.month,
            total=round(float(r.total), 2),
            count=r.count,
        )
        for r in rows
    ]
