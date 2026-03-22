"""
Property & Mortgage endpoints.

Provides mortgage details, amortization schedule, property valuation,
and Zillow estimate integration.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.property import Mortgage, PropertyValuation
from app.models.account import Account

router = APIRouter(prefix="/api/property", tags=["property"])


@router.get("/summary")
def property_summary(db: Session = Depends(get_db)):
    """Full property summary: mortgage, valuation, equity, payment breakdown."""
    # Get mortgage
    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    # Get property account and latest valuation
    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

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
        escrow = getattr(mortgage, 'escrow_payment', None)
        if escrow:
            escrow = float(escrow)
        else:
            escrow = 0  # Will be calculated from payment - principal - interest
        principal_portion = total_payment - interest_portion - escrow
        payment_breakdown = {
            "total": total_payment,
            "principal": round(principal_portion, 2),
            "interest": round(interest_portion, 2),
            "escrow": round(escrow, 2),
        }

    return {
        "property": {
            "address": prop_account.name if prop_account else None,
            "account_id": prop_account.id if prop_account else None,
            "value": property_value,
            "valuation_date": latest_valuation.valuation_date.isoformat() if latest_valuation else None,
            "valuation_source": latest_valuation.source if latest_valuation else None,
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
def amortization_schedule(db: Session = Depends(get_db)):
    """Compute full amortization from origination to payoff, marking current position."""
    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    if not mortgage or not mortgage.rate or not mortgage.monthly_payment:
        return {"schedule": [], "summary": None}

    monthly_rate = float(mortgage.rate) / 12
    payment = float(mortgage.monthly_payment)
    escrow = 0  # Estimated from total payment - P&I
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
def add_valuation(body: ValuationInput, db: Session = Depends(get_db)):
    """Add a property valuation (manual or from external source)."""
    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

    if not prop_account:
        raise HTTPException(status_code=404, detail="No real estate account found")

    val_date = date.fromisoformat(body.valuation_date) if body.valuation_date else date.today()

    pv = PropertyValuation(
        account_id=prop_account.id,
        valuation_date=val_date,
        value=Decimal(str(body.value)),
        source=body.source,
    )
    db.add(pv)
    db.commit()

    return {"id": pv.id, "value": float(pv.value), "date": pv.valuation_date.isoformat(), "source": pv.source}


@router.get("/valuation-history")
def valuation_history(db: Session = Depends(get_db)):
    """Historical property valuations over time."""
    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

    if not prop_account:
        return {"valuations": []}

    valuations = db.execute(
        select(PropertyValuation)
        .where(PropertyValuation.account_id == prop_account.id)
        .order_by(PropertyValuation.valuation_date)
    ).scalars().all()

    return {
        "valuations": [
            {
                "date": v.valuation_date.isoformat(),
                "value": float(v.value),
                "source": v.source,
            }
            for v in valuations
        ]
    }


@router.get("/zillow-estimate")
def zillow_estimate(db: Session = Depends(get_db)):
    """Fetch a property value estimate. Uses web scraping as a best-effort approach."""
    prop_account = db.execute(
        select(Account).where(Account.account_type == "real_estate").limit(1)
    ).scalar_one_or_none()

    if not prop_account:
        raise HTTPException(status_code=404, detail="No real estate account found")

    address = prop_account.name  # e.g. "456 Oak Street Springfield MA 01101"

    # Try to fetch from Zillow via web scraping
    import urllib.request
    import json
    import re

    # Format address for Zillow URL
    addr_parts = address.replace(",", "").split()
    zillow_slug = "-".join(addr_parts)
    url = f"https://www.zillow.com/homes/{zillow_slug}_rb/"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="ignore")

        # Look for Zestimate in the page
        # Zillow embeds data in JSON-LD or script tags
        zestimate = None
        # Try JSON-LD pattern
        match = re.search(r'"zestimate"\s*:\s*(\d+)', html)
        if match:
            zestimate = int(match.group(1))
        else:
            # Try price pattern
            match = re.search(r'\$(\d{1,3}(?:,\d{3})+)', html)
            if match:
                zestimate = int(match.group(1).replace(",", ""))

        if zestimate:
            # Auto-save as a valuation
            pv = PropertyValuation(
                account_id=prop_account.id,
                valuation_date=date.today(),
                value=Decimal(str(zestimate)),
                source="Zillow",
            )
            db.add(pv)
            db.commit()

            return {"estimate": zestimate, "source": "Zillow", "date": date.today().isoformat(), "saved": True}

        return {"estimate": None, "source": "Zillow", "error": "Could not extract estimate from Zillow page"}

    except Exception as e:
        return {"estimate": None, "source": "Zillow", "error": str(e)}
