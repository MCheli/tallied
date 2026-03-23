"""
Fixed capital assets API — vehicles and future asset types.
"""
import json
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_tenant_db
from app.models.asset import Vehicle
from app.models.asset_value_history import AssetValueHistory

router = APIRouter(prefix="/assets", tags=["assets"])


# ── Vehicle Schemas ───────────────────────────────────────────────────────────

class VehicleCreate(BaseModel):
    year: int
    make: str
    model: str
    trim: Optional[str] = None
    vin: Optional[str] = None
    mileage: Optional[int] = None
    condition: Optional[str] = "good"
    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None
    notes: Optional[str] = None


class VehicleUpdate(BaseModel):
    mileage: Optional[int] = None
    condition: Optional[str] = None
    notes: Optional[str] = None
    purchase_price: Optional[float] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/vehicles")
def list_vehicles(db: Session = Depends(get_tenant_db)):
    """List all vehicles with current estimated values."""
    vehicles = db.execute(
        select(Vehicle).order_by(Vehicle.year.desc())
    ).scalars().all()

    return [_serialize_vehicle(v) for v in vehicles]


@router.post("/vehicles")
def create_vehicle(body: VehicleCreate, db: Session = Depends(get_tenant_db)):
    """Add a vehicle and estimate its value."""
    vehicle = Vehicle(
        year=body.year,
        make=body.make,
        model=body.model,
        trim=body.trim,
        vin=body.vin,
        mileage=body.mileage,
        condition=body.condition,
        purchase_price=Decimal(str(body.purchase_price)) if body.purchase_price else None,
        purchase_date=date.fromisoformat(body.purchase_date) if body.purchase_date else None,
        notes=body.notes,
    )
    db.add(vehicle)
    db.flush()

    # Auto-estimate value
    estimate = _estimate_value_simple(vehicle)
    if estimate:
        vehicle.estimated_value = Decimal(str(estimate))
        vehicle.value_last_updated = datetime.now()

    db.commit()
    db.refresh(vehicle)
    return _serialize_vehicle(vehicle)


@router.put("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, body: VehicleUpdate, db: Session = Depends(get_tenant_db)):
    """Update vehicle details."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    for key, val in body.model_dump(exclude_unset=True).items():
        if key == "purchase_price" and val is not None:
            setattr(vehicle, key, Decimal(str(val)))
        else:
            setattr(vehicle, key, val)

    db.commit()
    db.refresh(vehicle)
    return _serialize_vehicle(vehicle)


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_tenant_db)):
    """Remove a vehicle."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    # Delete associated value history
    db.execute(delete(AssetValueHistory).where(AssetValueHistory.vehicle_id == vehicle_id))
    db.delete(vehicle)
    db.commit()
    return {"deleted": True}


@router.post("/vehicles/{vehicle_id}/refresh-value")
def refresh_vehicle_value(vehicle_id: int, db: Session = Depends(get_tenant_db)):
    """Re-estimate the vehicle's market value using AI, including history and projections."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    result = _estimate_value_with_history(vehicle)
    if result and result.get("current_value"):
        current_value = result["current_value"]
        vehicle.estimated_value = Decimal(str(current_value))
        vehicle.value_last_updated = datetime.now()
        vehicle.valuation_notes = result.get("reasoning")

        # Clear existing AI estimates for this vehicle (keep manual entries)
        db.execute(
            delete(AssetValueHistory).where(
                AssetValueHistory.vehicle_id == vehicle_id,
                AssetValueHistory.source.in_(["ai_estimate", "purchase"]),
            )
        )
        db.flush()

        # Store purchase price entry if available
        if vehicle.purchase_price and vehicle.purchase_date:
            db.add(AssetValueHistory(
                vehicle_id=vehicle_id,
                date=vehicle.purchase_date,
                value=vehicle.purchase_price,
                source="purchase",
                is_projected=False,
            ))

        # Store historical values
        for entry in result.get("history", []):
            db.add(AssetValueHistory(
                vehicle_id=vehicle_id,
                date=date(entry["year"], 1, 1),
                value=Decimal(str(entry["value"])),
                source="ai_estimate",
                is_projected=False,
            ))

        # Store projected values
        for entry in result.get("projections", []):
            db.add(AssetValueHistory(
                vehicle_id=vehicle_id,
                date=date(entry["year"], 1, 1),
                value=Decimal(str(entry["value"])),
                source="ai_estimate",
                is_projected=True,
            ))

        db.commit()
        db.refresh(vehicle)
        return {
            "estimated_value": current_value,
            "updated": True,
            "reasoning": result.get("reasoning", ""),
        }

    # Fallback: try simple estimate
    simple = _estimate_value_simple(vehicle)
    if simple:
        vehicle.estimated_value = Decimal(str(simple))
        vehicle.value_last_updated = datetime.now()
        db.commit()
        db.refresh(vehicle)
        return {"estimated_value": simple, "updated": True}

    return {"estimated_value": None, "updated": False, "error": "Could not estimate value"}


@router.get("/vehicles/{vehicle_id}/value-history")
def get_vehicle_value_history(vehicle_id: int, db: Session = Depends(get_tenant_db)):
    """Returns the value history for a single vehicle."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    rows = db.execute(
        select(AssetValueHistory)
        .where(AssetValueHistory.vehicle_id == vehicle_id)
        .order_by(AssetValueHistory.date)
    ).scalars().all()

    return {
        "vehicle_id": vehicle_id,
        "history": [
            {
                "date": r.date.isoformat(),
                "value": float(r.value),
                "source": r.source,
                "is_projected": r.is_projected,
            }
            for r in rows
        ],
    }


@router.get("/value-history/aggregate")
def get_aggregate_value_history(db: Session = Depends(get_tenant_db)):
    """Returns combined value history across all vehicles for a cumulative chart."""
    vehicles = db.execute(select(Vehicle).order_by(Vehicle.id)).scalars().all()
    vehicle_map = {v.id: f"{v.year} {v.make} {v.model}" for v in vehicles}

    rows = db.execute(
        select(AssetValueHistory).order_by(AssetValueHistory.date)
    ).scalars().all()

    # Group by date string
    date_values: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    all_dates: set[str] = set()

    for r in rows:
        d = r.date.isoformat()
        all_dates.add(d)
        name = vehicle_map.get(r.vehicle_id, f"Vehicle {r.vehicle_id}")
        date_values[d][name] = float(r.value)

    sorted_dates = sorted(all_dates)
    vehicle_names = sorted(vehicle_map.values())

    # Build per-vehicle arrays
    vehicles_data: dict[str, list[Optional[float]]] = {name: [] for name in vehicle_names}
    totals: list[float] = []

    for d in sorted_dates:
        total = 0.0
        for name in vehicle_names:
            val = date_values[d].get(name)
            vehicles_data[name].append(val if val else None)
            total += val if val else 0
        totals.append(round(total, 2))

    # Also include is_projected flag per date
    date_projected: dict[str, bool] = {}
    for r in rows:
        d = r.date.isoformat()
        if r.is_projected:
            date_projected[d] = True

    is_projected = [date_projected.get(d, False) for d in sorted_dates]

    return {
        "dates": sorted_dates,
        "total": totals,
        "vehicles": vehicles_data,
        "is_projected": is_projected,
    }


@router.get("/summary")
def assets_summary(db: Session = Depends(get_tenant_db)):
    """Summary of all fixed assets."""
    vehicles = db.execute(select(Vehicle).order_by(Vehicle.id)).scalars().all()

    total_value = sum(float(v.estimated_value or 0) for v in vehicles)
    # Only sum purchase prices for vehicles that have them
    vehicles_with_purchase = [v for v in vehicles if v.purchase_price]
    total_purchase = sum(float(v.purchase_price) for v in vehicles_with_purchase)

    return {
        "total_value": round(total_value, 2),
        "total_purchase_price": round(total_purchase, 2) if vehicles_with_purchase else None,
        "total_depreciation": round(total_purchase - total_value, 2) if vehicles_with_purchase else None,
        "vehicle_count": len(vehicles),
        "vehicles": [_serialize_vehicle(v) for v in vehicles],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_vehicle(v: Vehicle) -> dict:
    return {
        "id": v.id,
        "year": v.year,
        "make": v.make,
        "model": v.model,
        "trim": v.trim,
        "vin": v.vin,
        "mileage": v.mileage,
        "condition": v.condition,
        "purchase_price": float(v.purchase_price) if v.purchase_price else None,
        "purchase_date": v.purchase_date.isoformat() if v.purchase_date else None,
        "estimated_value": float(v.estimated_value) if v.estimated_value else None,
        "value_last_updated": v.value_last_updated.isoformat() if v.value_last_updated else None,
        "notes": v.notes,
        "valuation_notes": v.valuation_notes,
        "depreciation": round(float(v.purchase_price or 0) - float(v.estimated_value or 0), 2) if v.purchase_price and v.estimated_value else None,
    }


def _estimate_value_simple(vehicle: Vehicle) -> Optional[float]:
    """Use Claude AI to estimate a vehicle's current market value (simple, no history)."""
    if not settings.anthropic_api_key:
        return None

    prompt = f"""Estimate the current fair market value of this vehicle in USD.

Vehicle: {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim or ''}
Mileage: {vehicle.mileage or 'unknown'} miles
Condition: {vehicle.condition or 'unknown'}

Return ONLY a single number (the dollar value estimate, no currency symbol, no commas).
Base your estimate on typical private-party sale prices for this vehicle in the current market.
Consider the age, mileage, condition, and market demand for this specific vehicle."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip().replace(",", "").replace("$", "")
        match = re.search(r'\d+', text)
        if match:
            return float(match.group())
    except Exception:
        pass

    return None


def _estimate_value_with_history(vehicle: Vehicle) -> Optional[dict]:
    """Use Claude AI to estimate a vehicle's value with historical and projected data."""
    if not settings.anthropic_api_key:
        return None

    current_year = date.today().year
    purchase_year = vehicle.purchase_date.year if vehicle.purchase_date else vehicle.year
    history_start = max(purchase_year, current_year - 5)

    prompt = f"""You are a vehicle valuation expert. Research and estimate values for this vehicle.

Vehicle: {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim or ''}
Mileage: {vehicle.mileage or 'unknown'} miles
Condition: {vehicle.condition or 'unknown'}
Purchase year: {purchase_year}

Based on typical market values from sources like KBB, Edmunds, and NADA:

1. Estimate the CURRENT fair market value (private-party sale)
2. Estimate historical values for each year from {history_start} to {current_year}
3. Project future values for the next 5 years ({current_year + 1} to {current_year + 5})
4. Consider the vehicle's condition, mileage, and typical depreciation curves

Return ONLY valid JSON (no markdown, no code fences) in this exact format:
{{
  "current_value": 25000,
  "history": [
    {{"year": {history_start}, "value": 35000}},
    ...
  ],
  "projections": [
    {{"year": {current_year + 1}, "value": 22000}},
    ...
  ],
  "reasoning": "Brief explanation of the valuation methodology and key factors."
}}

Important:
- All values should be integers (whole dollars)
- History should cover each year from {history_start} to {current_year}
- Projections should cover each year from {current_year + 1} to {current_year + 5}
- Use realistic depreciation curves for this specific make/model"""

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

        # Validate structure
        if "current_value" in result and isinstance(result.get("history"), list):
            return result
    except Exception:
        pass

    return None
