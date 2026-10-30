"""Salary vs RSU split for one W-2 year: the one definition Dashboard, Income and Planning use.

Imported W-2s often carry only box 1 wages. When base_salary and rsu_income are both
missing, RSU income is the sum of that year's actual vests (shares x FMV at vest, the
figure E*TRADE reports as taxable gain) and salary is the rest of box 1 plus the pre-tax
deductions box 1 leaves out, labelled source="vests" so the page can say where it came from.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models.income import W2Record
from app.models.investment import VestEvent


@dataclass
class CompSplit:
    salary: float
    rsu_income: float
    source: str  # "w2" (recorded on the W-2), "vests" (RSU from vest records), "none"

    @property
    def total(self) -> float:
        return self.salary + self.rsu_income


def rsu_income_from_vests(db: Session, year: int) -> float:
    total = db.execute(
        select(func.coalesce(func.sum(VestEvent.shares * VestEvent.fmv_at_vest), 0)).where(
            VestEvent.is_actual.is_(True), extract("year", VestEvent.vest_date) == year
        )
    ).scalar()
    return float(total or 0)


def comp_split(db: Session, w2: W2Record | None) -> CompSplit:
    if w2 is None:
        return CompSplit(0.0, 0.0, "none")
    if w2.base_salary or w2.rsu_income:
        return CompSplit(float(w2.base_salary or 0), float(w2.rsu_income or 0), "w2")
    # An imported W-2 records box 1 wages, which leave out pre-tax 401(k) deferrals and pre-tax benefits
    # (section 125, transit). Pay is that plus those deductions.
    gross = float(w2.gross_pay or 0) + pretax_deductions(w2)
    rsu = rsu_income_from_vests(db, w2.tax_year)
    if gross <= 0:
        return CompSplit(0.0, rsu, "vests" if rsu else "none")
    rsu = min(rsu, gross)
    return CompSplit(round(gross - rsu, 2), round(rsu, 2), "vests" if rsu else "w2")


def pay_view(db: Session, w2: W2Record) -> dict:
    """What the Income page shows for a W-2: total pay (box 1 plus the pre-tax deductions it leaves out)
    and the salary/RSU split every page shares."""
    split = comp_split(db, w2)
    entered_split = bool(w2.base_salary or w2.rsu_income)   # then gross_pay was entered as gross pay
    return {
        "total_pay": round(float(w2.gross_pay or 0) + (0.0 if entered_split else pretax_deductions(w2)), 2),
        "salary_split": split.salary,
        "rsu_split": split.rsu_income,
        "split_source": split.source,
    }


def pretax_deductions(w2: W2Record) -> float:
    """Pay that box 1 leaves out: pre-tax 401(k), section 125 (health/FSA) and transit benefits."""
    if w2.w2_wages and w2.gross_pay and float(w2.gross_pay) > float(w2.w2_wages):
        return 0.0   # gross_pay already holds gross pay (box 1 is in w2_wages)
    return float(w2.pretax_401k or 0) + float(w2.cafeteria_125 or 0) + float(w2.transit or 0)


def latest_w2(db: Session) -> W2Record | None:
    return db.execute(select(W2Record).order_by(W2Record.tax_year.desc()).limit(1)).scalar_one_or_none()
