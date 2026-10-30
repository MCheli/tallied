"""What counts as spending (PRODUCT.md decision D1), shared by Dashboard, Spending and Cash.

Spending = transactions with a negative amount whose category is not a transfer
or a loan/credit-card payment, net of refunds (positive amounts in a spending category). Those categories move money between the
household's own accounts (or pay a balance already counted elsewhere), so
counting them would double-count the mortgage payment and card payments.
"""
from __future__ import annotations

from sqlalchemy import and_, func, or_

from app.models.transaction import Transaction

EXCLUDED_CATEGORIES = frozenset({
    "Transfer",
    "Transfers",
    "Credit Card Payment",
    "Credit Card Payments",
    "Loan Payment",
    "Loan Payments",
    "Mortgage Payment",
    "Payment",
})


# Money in that is income, not a refund of something bought.
INCOME_CATEGORIES = frozenset({
    "paycheck", "paychecks", "salary", "wages", "bonus", "income", "other income", "interest", "dividend",
    "dividends", "tax refund", "rewards", "cashback", "deposit", "deposits",
})


def _refund():
    """A positive amount in a spending category (a return, a refunded deposit, a credit): it nets spending."""
    return and_(
        Transaction.amount > 0,
        Transaction.category.is_not(None),
        Transaction.category != "",
        Transaction.category.notin_(EXCLUDED_CATEGORIES),
        func.lower(Transaction.category).notin_(INCOME_CATEGORIES),
        or_(Transaction.category_group.is_(None), func.lower(Transaction.category_group) != "income"),
    )


def spending_filter(stmt):
    """Restrict a Transaction query to spending rows: money out, net of refunds in the same categories.

    Sums over these rows are net spending; an uncategorized positive amount is never assumed to be a refund.
    """
    money_out = and_(
        Transaction.amount < 0,
        or_(Transaction.category.is_(None), Transaction.category.notin_(EXCLUDED_CATEGORIES)),
    )
    return stmt.where(or_(money_out, _refund()))


def is_spending_category(category: str | None) -> bool:
    return (category or "") not in EXCLUDED_CATEGORIES
