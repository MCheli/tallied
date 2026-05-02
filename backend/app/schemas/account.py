from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    id: str | None = None
    name: str
    institution: str
    account_type: str
    display_group: str
    include_in_nw: bool = True
    notes: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    account_type: str | None = None
    display_group: str | None = None
    include_in_nw: bool | None = None
    notes: str | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    institution: str | None = None
    account_type: str
    display_group: str
    include_in_nw: bool
    is_active: bool = True
    notes: str | None = None
    source: str = "manual"  # derived from id prefix; populated in route
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AccountWithBalance(AccountResponse):
    current_balance: float | None = None
    balance_date: date | None = None
