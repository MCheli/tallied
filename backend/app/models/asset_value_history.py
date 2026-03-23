"""Asset value history — historical and projected values for vehicles."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssetValueHistory(Base):
    __tablename__ = "asset_value_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(Integer, ForeignKey("vehicles.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # "ai_estimate", "purchase", "manual"
    is_projected: Mapped[bool] = mapped_column(Boolean, default=False)  # True for future projections
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
