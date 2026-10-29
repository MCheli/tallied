"""Fixed capital asset models (vehicles, etc.)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    make: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    trim: Mapped[str | None] = mapped_column(String)
    vin: Mapped[str | None] = mapped_column(String)
    mileage: Mapped[int | None] = mapped_column(Integer)
    condition: Mapped[str | None] = mapped_column(String)  # excellent, very_good, good, fair, poor
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric)
    value_last_updated: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    valuation_notes: Mapped[str | None] = mapped_column(Text)  # AI reasoning for current valuation
    valuation_source: Mapped[str | None] = mapped_column(String)  # "ai" | "manual"
    valuation_model: Mapped[str | None] = mapped_column(String)  # model id that produced the estimate
    valuation_confidence: Mapped[str | None] = mapped_column(String)  # high | medium | low
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
