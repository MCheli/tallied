from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TransactionCreate(BaseModel):
    account_id: str
    date: date
    amount: float
    merchant: str | None = None
    category: str | None = None
    category_group: str | None = None
    is_recurring: bool = False
    notes: str | None = None
    source: str | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str | None = None
    date: date
    amount: float | None = None
    merchant: str | None = None
    category: str | None = None
    category_group: str | None = None
    is_recurring: bool
    notes: str | None = None
    source: str | None = None
    created_at: datetime | None = None


class TransactionFilter(BaseModel):
    from_date: date | None = None
    to_date: date | None = None
    category: str | None = None
    category_group: str | None = None
    account_id: str | None = None
    merchant: str | None = None


class CategorySummary(BaseModel):
    category: str
    category_group: str | None = None
    total: float
    count: int
    pct_of_total: float


class RecurringExpense(BaseModel):
    merchant: str
    category: str
    avg_monthly: float
    months_seen: int
    last_date: date


class MonthlySpending(BaseModel):
    month: str  # e.g. "2026-01"
    total: float
    count: int
