"""The provider interface: what a bank/broker connection must offer.

A provider turns a stored credential into a `ProviderSnapshot` of accounts,
balances and transactions in Tallied's own vocabulary. The scheduler does the
rest (account creation, balance snapshots, transaction upserts, job rows), so
adding a provider means implementing this module's protocol and registering
it in `providers/__init__.py`; nothing in the scheduler changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

# Account kinds a provider may report, mapped to Tallied's account_type and display_group.
KIND_TO_TYPE_AND_GROUP: dict[str, tuple[str, str]] = {
    "checking": ("cash", "Cash"),
    "savings": ("cash", "Cash"),
    "credit_card": ("credit_card", "Credit Cards"),
    "investment": ("investment_stock", "Investments"),
    "retirement": ("investment_401k", "Retirement"),
    "mortgage": ("loan_mortgage", "Home Equity"),
    "loan": ("loan_student", "Other Loans"),
    "real_estate": ("real_estate", "Home Equity"),
    "other": ("cash", "Cash"),
}

TYPE_TO_GROUP: dict[str, str] = dict(KIND_TO_TYPE_AND_GROUP.values())


class ProviderError(Exception):
    """A provider call failed in a way the user should see (bad token, revoked access, upstream down)."""

    def __init__(self, message: str, *, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ProviderTransaction:
    id: str
    date: date
    amount: Decimal
    merchant: str = ""
    category: str = ""
    category_group: str = ""
    pending: bool = False


@dataclass
class ProviderAccount:
    id: str
    name: str
    institution: str = ""
    kind: str = "other"
    balance: Decimal | None = None
    balance_date: date | None = None
    transactions: list[ProviderTransaction] = field(default_factory=list)


@dataclass
class ProviderSnapshot:
    accounts: list[ProviderAccount]
    warnings: list[str] = field(default_factory=list)


@dataclass
class AccountSyncConfig:
    """How one upstream account maps onto Tallied (from the provider's config table)."""

    external_id: str
    account_name: str
    institution: str
    account_type: str | None
    sync_balances: bool
    sync_transactions: bool
    local_account_id: str | None
    row: object  # the ORM row, so the scheduler can set local_account_id


@dataclass
class ProviderConnection:
    credential: str  # decrypted
    configs: dict[str, AccountSyncConfig]
    row: object  # the ORM link row, so the scheduler can set last_synced_at


class Provider(Protocol):
    name: str
    display_name: str

    def get_connection(self, db: Session) -> ProviderConnection | None:
        """The tenant's stored connection, or None when not connected."""

    async def fetch(self, credential: str) -> ProviderSnapshot:
        """Pull accounts, balances and recent transactions."""

    def rebind(self, cfg: AccountSyncConfig, external_id: str) -> None:
        """Point a stored config at a new upstream id (the bank connection was re-made upstream)."""


def type_and_group_for(kind: str | None, account_type: str | None = None) -> tuple[str, str]:
    """Resolve (account_type, display_group) from a stored type or a provider kind."""
    if account_type:
        return account_type, TYPE_TO_GROUP.get(account_type, "Cash")
    return KIND_TO_TYPE_AND_GROUP.get(kind or "other", KIND_TO_TYPE_AND_GROUP["other"])
