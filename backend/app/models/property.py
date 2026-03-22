from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Mortgage(Base):
    __tablename__ = "mortgages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("accounts.id"), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    origination_date: Mapped[Optional[date]] = mapped_column(Date)
    original_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    original_payoff_date: Mapped[Optional[date]] = mapped_column(Date)
    current_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    account = relationship("Account")


class PropertyValuation(Base):
    __tablename__ = "property_valuations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("accounts.id"), nullable=False)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    account = relationship("Account")
