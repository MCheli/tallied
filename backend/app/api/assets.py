"""
Fixed capital assets API — vehicles and future asset types.
"""
import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai import AIError, ai_available, extract  # noqa: F401
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
    db.commit()
    db.refresh(vehicle)
    # The value is estimated on request (POST /vehicles/{id}/refresh-value), never
    # synchronously here: adding a vehicle must not depend on the AI being available.
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
    """Estimate the vehicle's market value with Claude and store it as a labelled estimate.

    Claude supplies today's value, a confidence and a depreciation rate; the
    history and projection points are computed deterministically from those
    (services/valuation.py). Failure is an HTTP error, never a silent no-op.
    """
    from app.services.valuation import estimate_vehicle_value, vehicle_value_curve

    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    try:
        valuation, model_id = estimate_vehicle_value(vehicle)
    except AIError as e:
        raise HTTPException(status_code=e.status_code, detail=f"Valuation unavailable: {e}")

    today = date.today()
    history, projections = vehicle_value_curve(
        purchase_price=float(vehicle.purchase_price) if vehicle.purchase_price else None,
        purchase_year=vehicle.purchase_date.year if vehicle.purchase_date else None,
        current_value=float(valuation.current_value),
        current_year=today.year,
        annual_depreciation_pct=valuation.annual_depreciation_pct,
    )

    vehicle.estimated_value = Decimal(valuation.current_value)
    vehicle.value_last_updated = datetime.now()
    vehicle.valuation_notes = valuation.reasoning
    vehicle.valuation_source = "ai"
    vehicle.valuation_model = model_id
    vehicle.valuation_confidence = valuation.confidence

    # Replace the previous AI curve; manual rows are never touched.
    db.execute(
        delete(AssetValueHistory).where(
            AssetValueHistory.vehicle_id == vehicle_id,
            AssetValueHistory.source.in_(["ai_estimate", "purchase"]),
        )
    )
    db.flush()
    if vehicle.purchase_price and vehicle.purchase_date:
        db.add(AssetValueHistory(vehicle_id=vehicle_id, date=vehicle.purchase_date,
                                 value=vehicle.purchase_price, source="purchase", is_projected=False))
    for year, value in history:
        if vehicle.purchase_date and year == vehicle.purchase_date.year:
            continue
        db.add(AssetValueHistory(vehicle_id=vehicle_id, date=date(year, 1, 1) if year != today.year else today,
                                 value=value, source="ai_estimate", is_projected=False))
    for year, value in projections:
        db.add(AssetValueHistory(vehicle_id=vehicle_id, date=date(year, 1, 1), value=value,
                                 source="ai_estimate", is_projected=True))
    db.commit()
    db.refresh(vehicle)
    return {
        "estimated_value": float(vehicle.estimated_value),
        "updated": True,
        "confidence": valuation.confidence,
        "model": model_id,
        "reasoning": valuation.reasoning,
        "annual_depreciation_pct": valuation.annual_depreciation_pct,
    }


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
        "valuation_source": v.valuation_source,
        "valuation_model": v.valuation_model,
        "valuation_confidence": v.valuation_confidence,
        "depreciation": round(float(v.purchase_price or 0) - float(v.estimated_value or 0), 2) if v.purchase_price and v.estimated_value else None,
    }
