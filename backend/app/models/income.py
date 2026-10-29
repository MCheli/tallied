from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class W2Record(Base):
    __tablename__ = "w2_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_year: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    gross_pay: Mapped[Decimal | None] = mapped_column(Numeric)
    w2_wages: Mapped[Decimal | None] = mapped_column(Numeric)
    federal_tax: Mapped[Decimal | None] = mapped_column(Numeric)
    state_tax: Mapped[Decimal | None] = mapped_column(Numeric)
    social_security: Mapped[Decimal | None] = mapped_column(Numeric)
    medicare: Mapped[Decimal | None] = mapped_column(Numeric)
    pretax_401k: Mapped[Decimal | None] = mapped_column(Numeric)
    roth_401k: Mapped[Decimal | None] = mapped_column(Numeric)
    cafeteria_125: Mapped[Decimal | None] = mapped_column(Numeric)
    transit: Mapped[Decimal | None] = mapped_column(Numeric)
    employer_health: Mapped[Decimal | None] = mapped_column(Numeric)
    base_salary: Mapped[Decimal | None] = mapped_column(Numeric)
    rsu_income: Mapped[Decimal | None] = mapped_column(Numeric)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )
