"""Property value history — tax assessments, estimates, sales, and AI projections."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PropertyValueHistory(Base):
    __tablename__ = "property_value_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("accounts.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String, default="tax_assessment")  # tax_assessment, realtor_estimate, sale, ai_projection, manual
    is_projected: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON string with extra info
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
