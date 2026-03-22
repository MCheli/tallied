from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transaction_date", "date"),
        Index("ix_transaction_category_date", "category", "date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("accounts.id"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 4))
    merchant: Mapped[Optional[str]] = mapped_column(String)
    category: Mapped[Optional[str]] = mapped_column(String)
    category_group: Mapped[Optional[str]] = mapped_column(String)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    account = relationship("Account", back_populates="transactions")
