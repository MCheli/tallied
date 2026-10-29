from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlanVersion(Base):
    __tablename__ = "plan_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scenario_type: Mapped[str] = mapped_column(String, default="base")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    assumptions = relationship("PlanAssumption", back_populates="plan", cascade="all, delete-orphan")
    projections = relationship("PlanProjection", back_populates="plan", cascade="all, delete-orphan")


class PlanAssumption(Base):
    __tablename__ = "plan_assumptions"
    __table_args__ = (
        UniqueConstraint("plan_id", "key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(String, default="medium")

    plan = relationship("PlanVersion", back_populates="assumptions")


class PlanProjection(Base):
    __tablename__ = "plan_projections"
    __table_args__ = (
        UniqueConstraint("plan_id", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    salary: Mapped[Decimal | None] = mapped_column(Numeric)
    rsu_income: Mapped[Decimal | None] = mapped_column(Numeric)
    total_comp: Mapped[Decimal | None] = mapped_column(Numeric)
    cash: Mapped[Decimal | None] = mapped_column(Numeric)
    investments: Mapped[Decimal | None] = mapped_column(Numeric)
    company_stock: Mapped[Decimal | None] = mapped_column(Numeric)
    home_equity: Mapped[Decimal | None] = mapped_column(Numeric)
    retirement_bal: Mapped[Decimal | None] = mapped_column(Numeric)
    net_worth: Mapped[Decimal | None] = mapped_column(Numeric)
    withdrawal: Mapped[Decimal | None] = mapped_column(Numeric, default=0)

    plan = relationship("PlanVersion", back_populates="projections")


class ActualSnapshot(Base):
    __tablename__ = "actual_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash: Mapped[Decimal | None] = mapped_column(Numeric)
    investments: Mapped[Decimal | None] = mapped_column(Numeric)
    company_stock: Mapped[Decimal | None] = mapped_column(Numeric)
    home_equity: Mapped[Decimal | None] = mapped_column(Numeric)
    retirement_bal: Mapped[Decimal | None] = mapped_column(Numeric)
    net_worth: Mapped[Decimal | None] = mapped_column(Numeric)
    salary_ytd: Mapped[Decimal | None] = mapped_column(Numeric)
    rsu_income_ytd: Mapped[Decimal | None] = mapped_column(Numeric)
    total_comp_ytd: Mapped[Decimal | None] = mapped_column(Numeric)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("generated_at", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    method: Mapped[str | None] = mapped_column(String)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    cash: Mapped[Decimal | None] = mapped_column(Numeric)
    investments: Mapped[Decimal | None] = mapped_column(Numeric)
    company_stock: Mapped[Decimal | None] = mapped_column(Numeric)
    home_equity: Mapped[Decimal | None] = mapped_column(Numeric)
    retirement_bal: Mapped[Decimal | None] = mapped_column(Numeric)
    net_worth: Mapped[Decimal | None] = mapped_column(Numeric)


class ContributionConfig(Base):
    __tablename__ = "contribution_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    employee_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    employer_match: Mapped[Decimal | None] = mapped_column(Numeric)
    annual_irs_limit: Mapped[Decimal | None] = mapped_column(Numeric)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )
