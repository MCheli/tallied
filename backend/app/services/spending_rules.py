"""What counts as spending (PRODUCT.md decision D1), shared by Dashboard, Spending and Cash.

Spending = transactions with a negative amount whose category is not a transfer
or a loan/credit-card payment. Those categories move money between the
household's own accounts (or pay a balance already counted elsewhere), so
counting them would double-count the mortgage payment and card payments.
"""
from __future__ import annotations

from sqlalchemy import or_

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


def spending_filter(stmt):
    """Restrict a Transaction query to spending rows."""
    return stmt.where(Transaction.amount < 0).where(
        or_(Transaction.category.is_(None), Transaction.category.notin_(EXCLUDED_CATEGORIES))
    )


def is_spending_category(category: str | None) -> bool:
    return (category or "") not in EXCLUDED_CATEGORIES
