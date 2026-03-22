"""401(k) / Retirement account models."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RetirementAccount(Base):
    """Top-level retirement account (e.g., ACME 401(K) SAVINGS PLAN)."""
    __tablename__ = "retirement_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String)  # T. Rowe Price
    account_id: Mapped[Optional[str]] = mapped_column(String)  # linked to accounts table

    # Current balances
    total_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    vested_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)

    # Balance by contribution type
    roth_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    pretax_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    employer_match_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    other_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # QNEC, etc.

    # Contribution rates
    pretax_deferral_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # e.g., 0.08 = 8%
    roth_deferral_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # e.g., 0.02 = 2%

    # Lifetime contributions
    total_employee_contributions: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    total_employer_contributions: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    roth_basis: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # Total Roth contributions (for tax purposes)

    # Performance
    account_return: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # e.g., 0.1474 = 14.74%
    return_period_start: Mapped[Optional[date]] = mapped_column(Date)

    # Statement period
    statement_start: Mapped[Optional[date]] = mapped_column(Date)
    statement_end: Mapped[Optional[date]] = mapped_column(Date)

    # Retirement projections
    estimated_monthly_income: Mapped[Optional[Decimal]] = mapped_column(Numeric)

    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class RetirementHolding(Base):
    """Individual fund/investment within the retirement account."""
    __tablename__ = "retirement_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retirement_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fund_name: Mapped[str] = mapped_column(String, nullable=False)
    ticker: Mapped[Optional[str]] = mapped_column(String)  # e.g., TRRGX for Target 2055
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    allocation_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # e.g., 1.0 = 100%
    gain_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric)

    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class RetirementSnapshot(Base):
    """Historical balance snapshot for tracking growth over time."""
    __tablename__ = "retirement_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retirement_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    roth_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    pretax_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    employer_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    source: Mapped[Optional[str]] = mapped_column(String)  # "statement", "manual"
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
