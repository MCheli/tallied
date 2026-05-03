from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from app.database import year_month
from app.dependencies import get_tenant_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.transaction import CategorySummary, RecurringExpense, MonthlySpending

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
    """Category totals for a date range (expenses only, amount < 0)."""
    stmt = (
        select(
            Transaction.category,
            Transaction.category_group,
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
        .where(Transaction.amount < 0)
        .where(Transaction.source != "plaid")
        .group_by(Transaction.category, Transaction.category_group)
        .order_by(func.sum(Transaction.amount))
    )

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
    months: int = Query(6, ge=1, le=24, description="Lookback months"),
    account_types: str | None = Query(None, description="Comma-separated account_types to include"),
    db: Session = Depends(get_tenant_db),
):
    """Detect recurring expenses by merchant frequency."""
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=months * 30)

    stmt = (
        select(
            Transaction.merchant,
            Transaction.category,
            func.avg(Transaction.amount).label("avg_amount"),
            func.count(func.distinct(
                year_month(Transaction.date)
            )).label("months_seen"),
            func.max(Transaction.date).label("last_date"),
        )
        .where(Transaction.amount < 0)
        .where(Transaction.source != "plaid")
        .where(Transaction.date >= cutoff)
        .where(Transaction.merchant.isnot(None))
        .group_by(Transaction.merchant, Transaction.category)
        .having(
            func.count(func.distinct(
                year_month(Transaction.date)
            )) >= max(2, months // 3)
        )
        .order_by(func.avg(Transaction.amount))
    )
    stmt = _apply_account_type_filter(stmt, _parse_account_types(account_types))

    rows = db.execute(stmt).all()

    return [
        RecurringExpense(
            merchant=r.merchant,
            category=r.category or "Uncategorized",
            avg_monthly=round(abs(float(r.avg_amount)), 2),
            months_seen=r.months_seen,
            last_date=r.last_date,
        )
        for r in rows
    ]


@router.get("/monthly-trend", response_model=list[MonthlySpending])
def monthly_spending_trend(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    account_types: str | None = Query(None, description="Comma-separated account_types to include"),
    db: Session = Depends(get_tenant_db),
):
    """Monthly spending totals."""
    stmt = (
        select(
            year_month(Transaction.date).label("month"),
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
        .where(Transaction.amount < 0)
        .where(Transaction.source != "plaid")
        .group_by("month")
        .order_by("month")
    )

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
