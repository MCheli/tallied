from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    institution: Mapped[Optional[str]] = mapped_column(String)
    account_type: Mapped[str] = mapped_column(String, nullable=False)
    display_group: Mapped[str] = mapped_column(String, nullable=False)
    include_in_nw: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_date: Mapped[Optional[date]] = mapped_column(Date)
    closed_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    balance_snapshots = relationship("BalanceSnapshot", back_populates="account")
    transactions = relationship("Transaction", back_populates="account")
