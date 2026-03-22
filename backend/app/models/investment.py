from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RSUGrant(Base):
    __tablename__ = "rsu_grants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    company: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(String)
    grant_date: Mapped[Optional[date]] = mapped_column(Date)
    total_shares: Mapped[Optional[int]] = mapped_column(Integer)
    vested_shares: Mapped[Optional[int]] = mapped_column(Integer)
    unvested_shares: Mapped[Optional[int]] = mapped_column(Integer)
    sellable_shares: Mapped[Optional[int]] = mapped_column(Integer)
    share_price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    vest_events = relationship("VestEvent", back_populates="grant", order_by="VestEvent.vest_date")


class VestEvent(Base):
    __tablename__ = "vest_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grant_id: Mapped[str] = mapped_column(String, ForeignKey("rsu_grants.id"), nullable=False)
    vest_date: Mapped[date] = mapped_column(Date, nullable=False)
    vest_period: Mapped[Optional[int]] = mapped_column(Integer)  # 1, 2, 3...
    shares: Mapped[int] = mapped_column(Integer, nullable=False)  # gross shares vesting
    fmv_at_vest: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # FMV per share at vest = cost basis
    shares_withheld: Mapped[Optional[int]] = mapped_column(Integer)  # shares sold for tax
    shares_released: Mapped[Optional[int]] = mapped_column(Integer)  # net shares after withholding
    total_taxes_paid: Mapped[Optional[Decimal]] = mapped_column(Numeric)  # total tax $ withheld
    is_actual: Mapped[bool] = mapped_column(Boolean, default=False)  # True = already vested

    # Legacy field kept for compatibility; prefer fmv_at_vest
    vest_price: Mapped[Optional[Decimal]] = mapped_column(Numeric)

    grant = relationship("RSUGrant", back_populates="vest_events")


class StockPrice(Base):
    __tablename__ = "stock_prices"
    __table_args__ = (
        UniqueConstraint("symbol", "price_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String)
