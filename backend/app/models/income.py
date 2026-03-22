from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class W2Record(Base):
    __tablename__ = "w2_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_year: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    gross_pay: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    w2_wages: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    federal_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    state_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    social_security: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    medicare: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    pretax_401k: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    roth_401k: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    cafeteria_125: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    transit: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    employer_health: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    base_salary: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    rsu_income: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
