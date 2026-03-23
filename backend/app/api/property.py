"""
Property & Mortgage endpoints.

Provides mortgage details, amortization schedule, property valuation,
and Realtor.com / AI estimate integration.
"""
import json
import logging
import re
import urllib.request
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
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

class MortgageUpdate(BaseModel):
    rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    current_balance: Optional[float] = None
    escrow: Optional[float] = None


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
    source_map = {
        "Manual": "manual",
        "Redfin": "manual",
        "Zillow": "manual",
        "Appraisal": "manual",
        "Tax Assessment": "tax_assessment",
    }
    history_source = source_map.get(body.source, "manual")
    pvh = PropertyValueHistory(
        account_id=prop_account.id,
        date=val_date,
        value=Decimal(str(body.value)),
        source=history_source,
        is_projected=False,
        details=json.dumps({"valuation_source": body.source}),
    )
    db.add(pvh)
    db.commit()

    return {"id": pv.id, "value": float(pv.value), "date": pv.valuation_date.isoformat(), "source": pv.source}


@router.put("/mortgage")
def update_mortgage(body: MortgageUpdate, db: Session = Depends(get_tenant_db)):
    """Update mortgage details (rate, payment, balance, escrow)."""
    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    if not mortgage:
        raise HTTPException(status_code=404, detail="No mortgage found")

    if body.rate is not None:
        mortgage.rate = Decimal(str(body.rate))
    if body.monthly_payment is not None:
        mortgage.monthly_payment = Decimal(str(body.monthly_payment))
    if body.current_balance is not None:
        mortgage.current_balance = Decimal(str(body.current_balance))
    if body.escrow is not None:
        mortgage.escrow = Decimal(str(body.escrow))

    db.commit()
    db.refresh(mortgage)
    return {
        "id": mortgage.id,
        "rate": float(mortgage.rate),
        "monthly_payment": float(mortgage.monthly_payment),
        "current_balance": float(mortgage.current_balance) if mortgage.current_balance else None,
        "escrow": float(mortgage.escrow) if mortgage.escrow else None,
    }


@router.delete("/valuation/{valuation_id}", status_code=204)
def delete_valuation(valuation_id: int, db: Session = Depends(get_tenant_db)):
    """Delete a property valuation entry."""
    pv = db.get(PropertyValuation, valuation_id)
    if not pv:
        raise HTTPException(status_code=404, detail="Valuation not found")
    db.delete(pv)
    db.commit()
    return None


@router.get("/valuation-history")
def valuation_history(db: Session = Depends(get_tenant_db)):
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


def _do_property_estimate(db: Session):
    """Estimate property value.  Priority: Realtor.com API > AI fallback."""
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

    # Resolve best available address
    address = (
        (mortgage.property_address if mortgage else None)
        or prop_account.name
    )
    if not address or address == "Primary Residence":
        raise HTTPException(status_code=400, detail="No property address available. Update your mortgage with a property address first.")

    # ── 1. Try Realtor.com API (via RapidAPI) ────────────────────────────
    realtor_error: Optional[str] = None
    try:
        result = get_property_estimate(address)
        if result and result.get("estimate"):
            estimate = result["estimate"]
            pv = PropertyValuation(
                account_id=prop_account.id,
                valuation_date=date.today(),
                value=Decimal(str(estimate)),
                source="Realtor.com",
            )
            db.add(pv)
            db.commit()
            return {
                "estimate": estimate,
                "source": "Realtor.com",
                "date": date.today().isoformat(),
                "saved": True,
                "details": result.get("details"),
            }
        if result is None and not settings.rapidapi_key:
            realtor_error = "RapidAPI key not configured"
        else:
            realtor_error = "No estimate returned from Realtor.com"
    except Exception as e:
        realtor_error = str(e)
        log.info("Realtor.com API failed for %s: %s", address, realtor_error)

    # No fallback — if Realtor.com doesn't have the property, suggest manual entry
    return {
        "estimate": None,
        "source": None,
        "error": f"Property not found on Realtor.com. Please enter a valuation manually using Zillow, Redfin, or a recent appraisal.",
    }


@router.post("/estimate")
def property_estimate(db: Session = Depends(get_tenant_db)):
    """Estimate property value.  Tries Realtor.com API first, then falls back to AI."""
    return _do_property_estimate(db)


@router.post("/zillow-estimate")
def property_estimate_legacy(db: Session = Depends(get_tenant_db)):
    """Legacy alias for /estimate — kept for backwards compatibility."""
    return _do_property_estimate(db)


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

    # d) AI projections for next 5 years
    commentary = None
    ai_projections = _ai_property_projections(address, tax_history, estimate, details)
    if ai_projections:
        commentary = ai_projections.get("commentary")
        for proj in ai_projections.get("projections", []):
            year = proj.get("year")
            value = proj.get("value")
            if year and value:
                db.add(PropertyValueHistory(
                    account_id=prop_account.id,
                    date=date(year, 1, 1),
                    value=Decimal(str(value)),
                    source="ai_projection",
                    is_projected=True,
                    details=json.dumps({
                        "commentary": commentary,
                        "property_details": details,
                    }),
                ))

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
        "refreshed": True,
    }


# ── Private helpers ──────────────────────────────────────────────────────────



def _ai_property_estimate(address: str, mortgage: Optional[Mortgage]) -> Optional[dict]:
    """Use Claude to estimate property value based on address and mortgage context."""
    if not settings.anthropic_api_key:
        return None

    # Build context from mortgage data
    context_parts = [f"Address: {address}"]
    if mortgage:
        if mortgage.original_amount:
            context_parts.append(f"Original purchase price / loan amount: ${float(mortgage.original_amount):,.0f}")
        if mortgage.origination_date:
            context_parts.append(f"Purchase / origination date: {mortgage.origination_date.isoformat()}")
        if mortgage.rate:
            context_parts.append(f"Mortgage rate: {float(mortgage.rate) * 100:.2f}%")

    context_str = "\n".join(context_parts)

    prompt = f"""You are a real estate valuation expert. Estimate the current fair market value
of the following residential property based on the address, location, and any available context.

{context_str}

Consider:
- Comparable home values in the area
- General market trends for this region
- Property type typical for this address
- Any context from the mortgage data

Return ONLY valid JSON (no markdown, no code fences) in this exact format:
{{
  "estimated_value": 520000,
  "confidence": "medium",
  "reasoning": "Brief explanation of the valuation methodology and key factors."
}}

Important:
- estimated_value should be an integer (whole dollars)
- confidence should be "low", "medium", or "high"
- Be conservative — this is a rough estimate without seeing the actual property"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        result = json.loads(text)
        if "estimated_value" in result:
            return result
    except Exception as exc:
        log.warning("AI property estimation failed: %s", exc)

    return None


def _ai_property_projections(
    address: str,
    tax_history: list[dict],
    current_estimate: Optional[int],
    details: Optional[dict],
) -> Optional[dict]:
    """Use Claude to project property values for the next 5 years."""
    if not settings.anthropic_api_key:
        return None

    current_year = date.today().year

    # Build historical context
    history_lines = []
    for t in sorted(tax_history, key=lambda x: x.get("year", 0)):
        year = t.get("year")
        val = t.get("assessed_value")
        if year and val:
            history_lines.append(f"  {year}: ${val:,} (tax assessment)")

    if current_estimate:
        history_lines.append(f"  {current_year} (today): ${current_estimate:,} (Realtor.com estimate)")

    history_str = "\n".join(history_lines) if history_lines else "No historical data available."

    # Property details
    detail_parts = [f"Address: {address}"]
    if details:
        if details.get("beds"):
            detail_parts.append(f"Beds: {details['beds']}")
        if details.get("baths"):
            detail_parts.append(f"Baths: {details['baths']}")
        if details.get("sqft"):
            detail_parts.append(f"Sqft: {details['sqft']}")
        if details.get("year_built"):
            detail_parts.append(f"Year built: {details['year_built']}")
        if details.get("last_sold_price"):
            detail_parts.append(f"Last sold: ${details['last_sold_price']:,}")
        if details.get("last_sold_date"):
            detail_parts.append(f"Last sold date: {details['last_sold_date']}")

    detail_str = "\n".join(detail_parts)

    projection_years = list(range(current_year + 1, current_year + 9))

    prompt = f"""You are a real estate market analyst. Based on the following property data, project the property's value for the next 8 years and provide commentary on the entire value timeline.

Property Details:
{detail_str}

Historical Values:
{history_str}

Task:
1. Project the property value for years {projection_years[0]} through {projection_years[-1]} (8 years)
2. Provide commentary analyzing the full timeline — past appreciation trends AND future outlook

Do NOT re-estimate current or past values. Only project future values.

Return ONLY valid JSON (no markdown, no code fences) in this exact format:
{{
  "projections": [
    {{"year": {projection_years[0]}, "value": 615000}},
    {{"year": {projection_years[1]}, "value": 632000}},
    {{"year": {projection_years[2]}, "value": 650000}},
    {{"year": {projection_years[3]}, "value": 669000}},
    {{"year": {projection_years[4]}, "value": 689000}},
    {{"year": {projection_years[5]}, "value": 710000}},
    {{"year": {projection_years[6]}, "value": 731000}},
    {{"year": {projection_years[7]}, "value": 753000}}
  ],
  "commentary": "A 2-3 sentence analysis of the property's value history and projected trajectory. Include the location context, appreciation trends, and market outlook."
}}

Important:
- Values should be integers (whole dollars)
- Base projections on local market conditions and historical appreciation rates
- Be realistic — typical residential appreciation is 2-5% annually
- The commentary should reference the specific location and its market dynamics"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        result = json.loads(text)
        if "projections" in result:
            return result
    except Exception as exc:
        log.warning("AI property projection failed: %s", exc)

    return None
