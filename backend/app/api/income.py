from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db
from app.models.income import W2Record
from app.models.investment import RSUGrant
from app.schemas.snapshot import IncomeBreakdown

from pydantic import BaseModel

router = APIRouter(prefix="/income", tags=["income"])


class W2Input(BaseModel):
    tax_year: int
    gross_pay: float | None = None
    w2_wages: float | None = None
    federal_tax: float | None = None
    state_tax: float | None = None
    social_security: float | None = None
    medicare: float | None = None
    pretax_401k: float | None = None
    roth_401k: float | None = None
    cafeteria_125: float | None = None
    transit: float | None = None
    employer_health: float | None = None
    base_salary: float | None = None
    rsu_income: float | None = None


@router.get("/history")
def income_history(db: Session = Depends(get_tenant_db)):
    """W2 records across years + RSU grant summary."""
    w2s = db.execute(
        select(W2Record).order_by(W2Record.tax_year.desc())
    ).scalars().all()

    grants = db.execute(
        select(RSUGrant).order_by(RSUGrant.grant_date.desc())
    ).scalars().all()

    w2_list = []
    for w in w2s:
        w2_list.append({
            "id": w.id,
            "tax_year": w.tax_year,
            "gross_pay": float(w.gross_pay) if w.gross_pay else None,
            "w2_wages": float(w.w2_wages) if w.w2_wages else None,
            "federal_tax": float(w.federal_tax) if w.federal_tax else None,
            "state_tax": float(w.state_tax) if w.state_tax else None,
            "social_security": float(w.social_security) if w.social_security else None,
            "medicare": float(w.medicare) if w.medicare else None,
            "pretax_401k": float(w.pretax_401k) if w.pretax_401k else None,
            "roth_401k": float(w.roth_401k) if w.roth_401k else None,
            "cafeteria_125": float(w.cafeteria_125) if w.cafeteria_125 else None,
            "transit": float(w.transit) if w.transit else None,
            "employer_health": float(w.employer_health) if w.employer_health else None,
            "base_salary": float(w.base_salary) if w.base_salary else None,
            "rsu_income": float(w.rsu_income) if w.rsu_income else None,
        })

    grant_list = []
    for g in grants:
        grant_list.append({
            "id": g.id,
            "company": g.company,
            "grant_date": g.grant_date.isoformat() if g.grant_date else None,
            "total_shares": g.total_shares,
            "vested_shares": g.vested_shares,
            "unvested_shares": g.unvested_shares,
            "sellable_shares": g.sellable_shares,
            "share_price": float(g.share_price) if g.share_price else None,
        })

    return {"w2_records": w2_list, "rsu_grants": grant_list}


@router.get("/current", response_model=IncomeBreakdown)
def current_income(db: Session = Depends(get_tenant_db)):
    """Current year income breakdown (latest W2 + RSU grants)."""
    current_year = date.today().year

    w2 = db.execute(
        select(W2Record).order_by(W2Record.tax_year.desc()).limit(1)
    ).scalar_one_or_none()

    if not w2:
        return IncomeBreakdown(salary=0, rsu_income=0, total_comp=0, rsu_pct=0)

    salary = float(w2.base_salary) if w2.base_salary else 0.0
    rsu_income = float(w2.rsu_income) if w2.rsu_income else 0.0
    total_comp = salary + rsu_income
    rsu_pct = (rsu_income / total_comp * 100) if total_comp > 0 else 0.0

    return IncomeBreakdown(
        salary=salary,
        rsu_income=rsu_income,
        total_comp=total_comp,
        rsu_pct=round(rsu_pct, 1),
    )


def _serialize_w2(w: W2Record) -> dict:
    return {
        "id": w.id,
        "tax_year": w.tax_year,
        "gross_pay": float(w.gross_pay) if w.gross_pay else None,
        "w2_wages": float(w.w2_wages) if w.w2_wages else None,
        "federal_tax": float(w.federal_tax) if w.federal_tax else None,
        "state_tax": float(w.state_tax) if w.state_tax else None,
        "social_security": float(w.social_security) if w.social_security else None,
        "medicare": float(w.medicare) if w.medicare else None,
        "pretax_401k": float(w.pretax_401k) if w.pretax_401k else None,
        "roth_401k": float(w.roth_401k) if w.roth_401k else None,
        "cafeteria_125": float(w.cafeteria_125) if w.cafeteria_125 else None,
        "transit": float(w.transit) if w.transit else None,
        "employer_health": float(w.employer_health) if w.employer_health else None,
        "base_salary": float(w.base_salary) if w.base_salary else None,
        "rsu_income": float(w.rsu_income) if w.rsu_income else None,
    }


@router.post("/w2", status_code=201)
def create_or_update_w2(payload: W2Input, db: Session = Depends(get_tenant_db)):
    """Create or update a W2 record for a given tax year."""
    existing = db.execute(
        select(W2Record).where(W2Record.tax_year == payload.tax_year)
    ).scalar_one_or_none()

    if existing:
        update_data = payload.model_dump(exclude_unset=True, exclude={"tax_year"})
        for key, value in update_data.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = W2Record(**payload.model_dump())
        db.add(record)
        db.commit()
        db.refresh(record)

    return _serialize_w2(record)


@router.get("/w2/{tax_year}")
def get_w2(tax_year: int, db: Session = Depends(get_tenant_db)):
    """Get a W2 record for a specific tax year."""
    w2 = db.execute(
        select(W2Record).where(W2Record.tax_year == tax_year)
    ).scalar_one_or_none()
    if not w2:
        raise HTTPException(status_code=404, detail="W2 record not found")
    return _serialize_w2(w2)


@router.put("/w2/{tax_year}")
def update_w2(tax_year: int, payload: W2Input, db: Session = Depends(get_tenant_db)):
    """Update a W2 record for a specific tax year."""
    w2 = db.execute(
        select(W2Record).where(W2Record.tax_year == tax_year)
    ).scalar_one_or_none()
    if not w2:
        raise HTTPException(status_code=404, detail="W2 record not found")

    update_data = payload.model_dump(exclude_unset=True, exclude={"tax_year"})
    for key, value in update_data.items():
        setattr(w2, key, value)
    db.commit()
    db.refresh(w2)
    return _serialize_w2(w2)


@router.delete("/w2/{tax_year}", status_code=204)
def delete_w2(tax_year: int, db: Session = Depends(get_tenant_db)):
    """Delete a W2 record for a specific tax year."""
    w2 = db.execute(
        select(W2Record).where(W2Record.tax_year == tax_year)
    ).scalar_one_or_none()
    if not w2:
        raise HTTPException(status_code=404, detail="W2 record not found")
    db.delete(w2)
    db.commit()
    return None
