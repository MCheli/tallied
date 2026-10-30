from datetime import date as _date
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransactionCreate(BaseModel):
    account_id: str
    date: _date
    amount: float
    merchant: str | None = None
    category: str | None = None
    category_group: str | None = None
    is_recurring: bool = False
    notes: str | None = None
    source: str | None = None


class TransactionUpdate(BaseModel):
    account_id: str | None = None
    date: _date | None = None
    amount: float | None = None
    merchant: str | None = None
    category: str | None = None
    category_group: str | None = None
    is_recurring: bool | None = None
    notes: str | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str | None = None
    date: _date
    amount: float | None = None
    merchant: str | None = None
    category: str | None = None
    category_group: str | None = None
    is_recurring: bool
    notes: str | None = None
    source: str | None = None
    category_source: str | None = None
    created_at: datetime | None = None


class TransactionFilter(BaseModel):
    from_date: _date | None = None
    to_date: _date | None = None
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
    last_date: _date


class MonthlySpending(BaseModel):
    month: str  # e.g. "2026-01"
    total: float
    count: int


class CategoryOption(BaseModel):
    category: str
    category_group: str | None = None


class CategoryRuleCreate(BaseModel):
    pattern: str
    match: str = "exact"
    category: str
    category_group: str
    account_type: str | None = None
    direction: str | None = None


class CategoryRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    match: str
    account_type: str | None = None
    direction: str | None = None
    category: str
    category_group: str
    source: str
    note: str | None = None
    priority: int


class CategoryRuleApplied(BaseModel):
    rule: CategoryRuleResponse
    recategorized: int
