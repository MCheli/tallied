"""
Fixed capital assets API — vehicles and future asset types.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai import AIError, ai_available, extract  # noqa: F401
from app.dependencies import get_tenant_db
from app.models.asset import Vehicle
from app.models.asset_value_history import AssetValueHistory
from app.services.valuation import MARKET, fleet_value_grid

router = APIRouter(prefix="/assets", tags=["assets"])


# ── Vehicle Schemas ───────────────────────────────────────────────────────────

class VehicleCreate(BaseModel):
    year: int
    make: str
    model: str
    trim: str | None = None
    vin: str | None = None
    mileage: int | None = None
    condition: str | None = "good"
    purchase_price: float | None = None
    purchase_date: str | None = None
    notes: str | None = None


class VehicleUpdate(BaseModel):
    mileage: int | None = None
    condition: str | None = None
    notes: str | None = None
    purchase_price: float | None = None


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
    from app.services.valuation import estimate_vehicle_value, store_vehicle_valuation

    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    try:
        valuation, model_id = estimate_vehicle_value(vehicle)
    except AIError as e:
        raise HTTPException(status_code=e.status_code, detail=f"Valuation unavailable: {e}")

    store_vehicle_valuation(db, vehicle, value=float(valuation.current_value),
                            annual_depreciation_pct=valuation.annual_depreciation_pct, reasoning=valuation.reasoning,
                            source="ai", model=model_id, confidence=valuation.confidence)
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
    line, purchase = curve_rows(rows)

    return {
        "vehicle_id": vehicle_id,
        "purchase": purchase,
        "history": [
            {
                "date": r.date.isoformat(),
                "value": float(r.value),
                "source": r.source,
                "is_projected": r.is_projected,
            }
            for r in line
        ],
    }


def curve_rows(rows) -> tuple[list, dict | None]:
    """(rows drawn as the vehicle's line, its purchase point). Researched market rows are reference data
    behind the line, never drawn. With a market curve the purchase is a marker, not a point on the line:
    a dealer price would otherwise show as a spike."""
    has_market = any(r.source == MARKET for r in rows)
    purchase = next(({"date": r.date.isoformat(), "value": float(r.value)} for r in rows if r.source == "purchase"), None)
    line = [r for r in rows if r.source != MARKET and not (has_market and r.source == "purchase")]
    return line, purchase


@router.get("/value-history/aggregate")
def get_aggregate_value_history(db: Session = Depends(get_tenant_db)):
    """Every vehicle's value on one shared list of dates, plus each purchase as a marker."""
    vehicles = db.execute(select(Vehicle).order_by(Vehicle.id)).scalars().all()
    names = [f"{v.year} {v.make} {v.model}" for v in vehicles]
    label = {v.id: (n if names.count(n) == 1 else f"{n} #{v.id}") for v, n in zip(vehicles, names)}
    by_vehicle: dict[int, list] = defaultdict(list)
    for r in db.execute(select(AssetValueHistory).order_by(AssetValueHistory.date)).scalars():
        if r.vehicle_id in label:
            by_vehicle[r.vehicle_id].append(r)
    points: dict[str, list[tuple[date, float, bool]]] = {}
    purchases = []
    for vid, rows in by_vehicle.items():
        line, purchase = curve_rows(rows)
        points[label[vid]] = [(r.date, float(r.value), r.is_projected) for r in line]
        if purchase:
            purchases.append({"vehicle": label[vid], **purchase})
    return {**fleet_value_grid(dict(sorted(points.items())), date.today()), "purchases": purchases}


@router.get("/summary")
def assets_summary(db: Session = Depends(get_tenant_db)):
    """Summary of all fixed assets."""
    vehicles = db.execute(select(Vehicle).order_by(Vehicle.id)).scalars().all()

    total_value = sum(float(v.estimated_value or 0) for v in vehicles)
    # Depreciation only makes sense per vehicle that has both a purchase price and an estimate.
    vehicles_with_purchase = [v for v in vehicles if v.purchase_price]
    total_purchase = sum(float(v.purchase_price) for v in vehicles_with_purchase)
    depreciable = [v for v in vehicles_with_purchase if v.estimated_value is not None]
    total_depreciation = sum(float(v.purchase_price) - float(v.estimated_value) for v in depreciable)

    return {
        "total_value": round(total_value, 2),
        "total_purchase_price": round(total_purchase, 2) if vehicles_with_purchase else None,
        "total_depreciation": round(total_depreciation, 2) if depreciable else None,
        "vehicles_with_purchase_price": len(vehicles_with_purchase),
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
