"""
Property & Mortgage endpoints.

Provides mortgage details, amortization schedule, property valuation,
and Realtor.com lookups with a labelled AI outlook for projections.
"""
import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import AIError, ai_available
from app.dependencies import get_tenant_db
from app.models.property import Mortgage, PropertyValuation
from app.models.property_value_history import PropertyValueHistory
from app.models.account import Account
from app.services.property_valuation import get_property_estimate

log = logging.getLogger(__name__)

router = APIRouter(prefix="/property", tags=["property"])


@router.get("/summary")
def property_summary(db: Session = Depends(get_tenant_db)):
    """Full property summary: mortgage, valuation, equity, payment breakdown."""
    # Get mortgage
    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    # Get property account and latest valuation
    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

    # Auto-create real_estate account when a mortgage exists but no property account
    if not prop_account and mortgage:
        address = mortgage.property_address or "Primary Residence"
        prop_account = Account(
            id=str(uuid.uuid4()),
            name=address,
            account_type="real_estate",
            display_group="Home Equity",
            include_in_nw=True,
        )
        db.add(prop_account)
        db.flush()

    latest_valuation = None
    if prop_account:
        latest_valuation = db.execute(
            select(PropertyValuation)
            .where(PropertyValuation.account_id == prop_account.id)
            .order_by(PropertyValuation.valuation_date.desc())
            .limit(1)
        ).scalar_one_or_none()

    # Compute equity
    property_value = float(latest_valuation.value) if latest_valuation else None
    mortgage_balance = float(mortgage.current_balance) if mortgage and mortgage.current_balance else None
    equity = None
    if property_value is not None and mortgage_balance is not None:
        equity = property_value - mortgage_balance

    # Payment breakdown (from mortgage statement: principal + interest + escrow = total)
    payment_breakdown = None
    if mortgage and mortgage.monthly_payment and mortgage.rate and mortgage.current_balance:
        monthly_rate = float(mortgage.rate) / 12
        bal = float(mortgage.current_balance)
        interest_portion = bal * monthly_rate
        total_payment = float(mortgage.monthly_payment)
        # Escrow is estimated from config or statement; default to what's left after P&I
        # For standard amortization: principal = payment - interest (if no escrow)
        # With escrow, we need to store it. For now estimate escrow from the statement data.
        escrow = float(mortgage.escrow) if mortgage.escrow else 0
        principal_portion = total_payment - interest_portion - escrow
        payment_breakdown = {
            "total": total_payment,
            "principal": round(principal_portion, 2),
            "interest": round(interest_portion, 2),
            "escrow": round(escrow, 2),
        }

    # Get purchase price from value history (sale entry)
    purchase_price = None
    purchase_date = None
    if prop_account:
        sale_entry = db.execute(
            select(PropertyValueHistory)
            .where(PropertyValueHistory.account_id == prop_account.id)
            .where(PropertyValueHistory.source == "sale")
            .order_by(PropertyValueHistory.date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if sale_entry:
            purchase_price = float(sale_entry.value)
            purchase_date = sale_entry.date.isoformat()

    return {
        "property": {
            "address": (mortgage.property_address if mortgage and mortgage.property_address else None) or (prop_account.name if prop_account else None),
            "account_id": prop_account.id if prop_account else None,
            "value": property_value,
            "valuation_date": latest_valuation.valuation_date.isoformat() if latest_valuation else None,
            "valuation_source": latest_valuation.source if latest_valuation else None,
            "purchase_price": purchase_price,
            "purchase_date": purchase_date,
        } if prop_account else None,
        "mortgage": {
            "balance": mortgage_balance,
            "rate": float(mortgage.rate) if mortgage and mortgage.rate else None,
            "monthly_payment": float(mortgage.monthly_payment) if mortgage and mortgage.monthly_payment else None,
            "original_amount": float(mortgage.original_amount) if mortgage and mortgage.original_amount else None,
            "origination_date": mortgage.origination_date.isoformat() if mortgage and mortgage.origination_date else None,
            "maturity_date": mortgage.original_payoff_date.isoformat() if mortgage and mortgage.original_payoff_date else None,
            "updated_at": mortgage.updated_at.isoformat() if mortgage and mortgage.updated_at else None,
        } if mortgage else None,
        "equity": equity,
        "payment_breakdown": payment_breakdown,
    }


@router.get("/amortization")
def amortization_schedule(db: Session = Depends(get_tenant_db)):
    """Compute full amortization from origination to payoff, marking current position."""
    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    if not mortgage or not mortgage.rate or not mortgage.monthly_payment:
        return {"schedule": [], "summary": None}

    monthly_rate = float(mortgage.rate) / 12
    payment = float(mortgage.monthly_payment)
    escrow = float(mortgage.escrow) if mortgage.escrow else 0
    today = date.today()

    # Start from origination with original balance
    original_amount = float(mortgage.original_amount) if mortgage.original_amount else float(mortgage.current_balance or 0)
    start_date = mortgage.origination_date or date(2022, 3, 31)

    balance = original_amount
    schedule = []
    total_interest_paid = 0.0
    total_principal_paid = 0.0
    total_interest_remaining = 0.0
    current_month_index = None
    month_date = start_date.replace(day=1)

    while balance > 0 and len(schedule) < 400:  # max ~33 years
        interest = balance * monthly_rate
        principal = payment - interest - escrow
        if principal <= 0:
            break
        if principal > balance:
            principal = balance
        balance -= principal

        # Advance month
        if month_date.month == 12:
            month_date = month_date.replace(year=month_date.year + 1, month=1)
        else:
            month_date = month_date.replace(month=month_date.month + 1)

        is_past = month_date <= today
        if is_past:
            total_interest_paid += interest
            total_principal_paid += principal
        else:
            total_interest_remaining += interest

        # Mark the current month
        if current_month_index is None and month_date >= today:
            current_month_index = len(schedule)

        schedule.append({
            "date": month_date.isoformat(),
            "principal": round(principal, 2),
            "escrow": round(escrow, 2),
            "interest": round(interest, 2),
            "balance": round(max(0, balance), 2),
            "is_past": is_past,
        })

    payoff_date = schedule[-1]["date"] if schedule else None
    months_remaining = len(schedule) - (current_month_index or 0)

    return {
        "schedule": schedule,
        "current_month_index": current_month_index,
        "summary": {
            "original_amount": original_amount,
            "current_balance": float(mortgage.current_balance) if mortgage.current_balance else None,
            "payoff_date": payoff_date,
            "months_remaining": months_remaining,
            "total_interest_paid": round(total_interest_paid, 2),
            "total_interest_remaining": round(total_interest_remaining, 2),
            "total_principal_paid": round(total_principal_paid, 2),
        },
    }

class ValuationInput(BaseModel):
    value: float
    source: str = "Manual"
    valuation_date: Optional[str] = None


@router.post("/valuation")
def add_valuation(body: ValuationInput, db: Session = Depends(get_tenant_db)):
    """Add a property valuation (manual or from external source)."""
    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

    # Auto-create real_estate account if mortgage exists
    if not prop_account:
        mortgage = db.execute(
            select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
        ).scalar_one_or_none()
        if mortgage:
            address = mortgage.property_address or "Primary Residence"
            prop_account = Account(
                id=str(uuid.uuid4()),
                name=address,
                account_type="real_estate",
                display_group="Home Equity",
                include_in_nw=True,
            )
            db.add(prop_account)
            db.flush()
        else:
            raise HTTPException(status_code=404, detail="No real estate account found. Import a mortgage first.")

    val_date = date.fromisoformat(body.valuation_date) if body.valuation_date else date.today()

    pv = PropertyValuation(
        account_id=prop_account.id,
        valuation_date=val_date,
        value=Decimal(str(body.value)),
        source=body.source,
    )
    db.add(pv)

    # Also add a PropertyValueHistory entry so manual valuations appear on the chart
    # Anything the owner typed is source="manual" so a Realtor.com refresh never
    # deletes it; the chosen label (Zillow, Appraisal, Tax Assessment, ...) is kept in details.
    pvh = PropertyValueHistory(
        account_id=prop_account.id,
        date=val_date,
        value=Decimal(str(body.value)),
        source="manual",
        is_projected=False,
        details=json.dumps({"valuation_source": body.source}),
    )
    db.add(pvh)
    db.commit()

    return {"id": pv.id, "value": float(pv.value), "date": pv.valuation_date.isoformat(), "source": pv.source}


# ── Property Value History ───────────────────────────────────────────────────


@router.get("/value-history")
def value_history(db: Session = Depends(get_tenant_db)):
    """Return the full property value history for charting."""
    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

    if not prop_account:
        return {"history": [], "commentary": None, "property_details": None}

    entries = db.execute(
        select(PropertyValueHistory)
        .where(PropertyValueHistory.account_id == prop_account.id)
        .order_by(PropertyValueHistory.date)
    ).scalars().all()

    # Extract commentary from the most recent ai_projection entry details
    commentary = None
    property_details = None
    for entry in reversed(list(entries)):
        if entry.source == "ai_projection" and entry.details:
            try:
                d = json.loads(entry.details)
                if "commentary" in d:
                    commentary = d["commentary"]
                if "property_details" in d:
                    property_details = d["property_details"]
                break
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "history": [
            {
                "date": e.date.isoformat(),
                "value": float(e.value),
                "source": e.source,
                "is_projected": e.is_projected,
            }
            for e in entries
        ],
        "commentary": commentary,
        "property_details": property_details,
    }


@router.post("/refresh-history")
def refresh_history(db: Session = Depends(get_tenant_db)):
    """Refresh property value history from Realtor.com + AI projections."""
    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

    # Auto-create real_estate account if mortgage exists
    if not prop_account and mortgage:
        address = mortgage.property_address or "Primary Residence"
        prop_account = Account(
            id=str(uuid.uuid4()),
            name=address,
            account_type="real_estate",
            display_group="Home Equity",
            include_in_nw=True,
        )
        db.add(prop_account)
        db.flush()

    if not prop_account:
        raise HTTPException(status_code=404, detail="No real estate account found. Import a mortgage first.")

    # Resolve address
    address = (
        (mortgage.property_address if mortgage else None)
        or prop_account.name
    )
    if not address or address == "Primary Residence":
        raise HTTPException(status_code=400, detail="No property address available.")

    # Clear existing non-manual history for this account (preserve manual entries)
    existing = db.execute(
        select(PropertyValueHistory).where(
            PropertyValueHistory.account_id == prop_account.id,
            PropertyValueHistory.source != "manual",
        )
    ).scalars().all()
    for entry in existing:
        db.delete(entry)
    db.flush()

    # Fetch data from Realtor.com
    realtor_data = None
    try:
        realtor_data = get_property_estimate(address)
    except Exception as e:
        log.warning("Realtor.com API failed: %s", e)

    if not realtor_data:
        raise HTTPException(status_code=502, detail="Could not fetch property data from Realtor.com.")

    details = realtor_data.get("details", {})
    tax_history = realtor_data.get("tax_history", [])

    # a) Tax assessment history entries (limit to 8 years)
    min_year = date.today().year - 8
    for tax in sorted(tax_history, key=lambda t: t.get("year", 0)):
        year = tax.get("year")
        assessed_value = tax.get("assessed_value")
        if year and assessed_value and year >= min_year:
            db.add(PropertyValueHistory(
                account_id=prop_account.id,
                date=date(year, 1, 1),
                value=Decimal(str(assessed_value)),
                source="tax_assessment",
                is_projected=False,
                details=json.dumps({"tax": tax.get("tax")}),
            ))

    # b) Sale price entry
    last_sold_price = details.get("last_sold_price")
    last_sold_date_str = details.get("last_sold_date")
    if last_sold_price and last_sold_date_str:
        try:
            sold_date = date.fromisoformat(last_sold_date_str)
        except (ValueError, TypeError):
            # Try to parse various date formats
            try:
                sold_date = datetime.strptime(str(last_sold_date_str), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                sold_date = None
        if sold_date:
            db.add(PropertyValueHistory(
                account_id=prop_account.id,
                date=sold_date,
                value=Decimal(str(last_sold_price)),
                source="sale",
                is_projected=False,
            ))

    # c) Current Realtor.com estimate
    estimate = realtor_data.get("estimate")
    if estimate:
        db.add(PropertyValueHistory(
            account_id=prop_account.id,
            date=date.today(),
            value=Decimal(str(estimate)),
            source="realtor_estimate",
            is_projected=False,
            details=json.dumps({"sources": realtor_data.get("sources", [])}),
        ))

        # Also update the property valuation so the summary cards reflect the latest estimate
        pv = PropertyValuation(
            account_id=prop_account.id,
            valuation_date=date.today(),
            value=Decimal(str(estimate)),
            source="Realtor.com",
        )
        db.add(pv)

    db.flush()

    # d) Outlook: Claude gives a yearly appreciation rate + commentary; the eight
    #    projected points are computed from it and stored as labelled estimates.
    commentary = None
    projection_note = None
    if estimate and ai_available():
        from app.services.valuation import estimate_property_outlook, property_projection

        try:
            outlook, model_id = estimate_property_outlook(address, tax_history, float(estimate), details)
        except AIError as e:
            log.warning("Property outlook unavailable for %s: %s", address, e)
            projection_note = f"AI outlook unavailable: {e}"
        else:
            commentary = outlook.commentary
            label = {
                "commentary": commentary,
                "property_details": details,
                "source": "ai",
                "model": model_id,
                "confidence": outlook.confidence,
                "annual_appreciation_pct": outlook.annual_appreciation_pct,
            }
            for year, value in property_projection(
                current_value=float(estimate), current_year=date.today().year,
                annual_appreciation_pct=outlook.annual_appreciation_pct,
            ):
                db.add(PropertyValueHistory(
                    account_id=prop_account.id, date=date(year, 1, 1), value=value,
                    source="ai_projection", is_projected=True, details=json.dumps(label),
                ))
    elif not ai_available():
        projection_note = "AI outlook skipped: FINANCE_ANTHROPIC_API_KEY is not configured"

    db.commit()

    # Return the refreshed history
    entries = db.execute(
        select(PropertyValueHistory)
        .where(PropertyValueHistory.account_id == prop_account.id)
        .order_by(PropertyValueHistory.date)
    ).scalars().all()

    return {
        "history": [
            {
                "date": e.date.isoformat(),
                "value": float(e.value),
                "source": e.source,
                "is_projected": e.is_projected,
            }
            for e in entries
        ],
        "commentary": commentary,
        "property_details": details,
        "projection_note": projection_note,
        "refreshed": True,
    }
