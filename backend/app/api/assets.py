"""
Fixed capital assets API — vehicles and future asset types.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.asset import Vehicle

router = APIRouter(prefix="/api/assets", tags=["assets"])


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
def list_vehicles(db: Session = Depends(get_db)):
    """List all vehicles with current estimated values."""
    vehicles = db.execute(
        select(Vehicle).order_by(Vehicle.year.desc())
    ).scalars().all()

    return [_serialize_vehicle(v) for v in vehicles]


@router.post("/vehicles")
def create_vehicle(body: VehicleCreate, db: Session = Depends(get_db)):
    """Add a vehicle and estimate its value."""
    from datetime import date as d

    vehicle = Vehicle(
        year=body.year,
        make=body.make,
        model=body.model,
        trim=body.trim,
        vin=body.vin,
        mileage=body.mileage,
        condition=body.condition,
        purchase_price=Decimal(str(body.purchase_price)) if body.purchase_price else None,
        purchase_date=d.fromisoformat(body.purchase_date) if body.purchase_date else None,
        notes=body.notes,
    )
    db.add(vehicle)
    db.flush()

    # Auto-estimate value
    estimate = _estimate_value(vehicle)
    if estimate:
        vehicle.estimated_value = Decimal(str(estimate))
        vehicle.value_last_updated = datetime.now()

    db.commit()
    db.refresh(vehicle)
    return _serialize_vehicle(vehicle)


@router.put("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, body: VehicleUpdate, db: Session = Depends(get_db)):
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
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    """Remove a vehicle."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    db.delete(vehicle)
    db.commit()
    return {"deleted": True}


@router.post("/vehicles/{vehicle_id}/refresh-value")
def refresh_vehicle_value(vehicle_id: int, db: Session = Depends(get_db)):
    """Re-estimate the vehicle's market value using AI."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    estimate = _estimate_value(vehicle)
    if estimate:
        vehicle.estimated_value = Decimal(str(estimate))
        vehicle.value_last_updated = datetime.now()
        db.commit()
        db.refresh(vehicle)
        return {"estimated_value": estimate, "updated": True}

    return {"estimated_value": None, "updated": False, "error": "Could not estimate value"}


@router.get("/summary")
def assets_summary(db: Session = Depends(get_db)):
    """Summary of all fixed assets."""
    vehicles = db.execute(select(Vehicle)).scalars().all()

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
        "depreciation": round(float(v.purchase_price or 0) - float(v.estimated_value or 0), 2) if v.purchase_price and v.estimated_value else None,
    }


def _estimate_value(vehicle: Vehicle) -> Optional[float]:
    """Use Claude AI to estimate a vehicle's market value."""
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
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip().replace(",", "").replace("$", "")
        # Extract first number from response
        import re
        match = re.search(r'\d+', text)
        if match:
            return float(match.group())
    except Exception:
        pass

    return None
