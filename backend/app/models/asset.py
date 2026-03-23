"""Fixed capital asset models (vehicles, etc.)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    make: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    trim: Mapped[Optional[str]] = mapped_column(String)
    vin: Mapped[Optional[str]] = mapped_column(String)
    mileage: Mapped[Optional[int]] = mapped_column(Integer)
    condition: Mapped[Optional[str]] = mapped_column(String)  # excellent, very_good, good, fair, poor
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    purchase_date: Mapped[Optional[date]] = mapped_column(Date)
    estimated_value: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    value_last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    valuation_notes: Mapped[Optional[str]] = mapped_column(Text)  # AI reasoning for current valuation
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
