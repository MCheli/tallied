"""Labelled AI estimates with deterministic projections (AI-3 / DEC-3).

Claude is asked for one number (today's value) plus a rate and reasoning; the
history and projection curves are computed here, so a chart never shows the
model's guesses about the past as fact, and every stored estimate carries its
source, model and confidence.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

from app.ai import extract, model_for
from app.ai.schemas import PropertyOutlook, VehicleValuation
from app.models.asset import Vehicle

VEHICLE_INSTRUCTIONS = """You are a vehicle valuation analyst. Estimate the private-party fair market
value in US dollars of the vehicle described by the user, considering age, mileage, condition, trim
and typical market demand, and give the yearly depreciation you expect over the next five years.
Be conservative. The reasoning is shown to the owner next to the number."""

PROPERTY_INSTRUCTIONS = """You are a residential real-estate market analyst. Given a property's
address, details and value history, give the yearly appreciation rate you expect over the next
eight years and two or three sentences of commentary on the location, recent trend and outlook.
Do not re-estimate the current value. Typical residential appreciation is 2 to 5 percent a year."""


MARKET = "market"   # researched comparable-sale values by date; reference data, not this vehicle's curve


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _money(value: float) -> Decimal:
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def vehicle_value_curve(
    *,
    purchase_price: float | None,
    purchase_date: date | None,
    current_value: float,
    today: date,
    annual_depreciation_pct: float,
    years_ahead: int = 5,
    market: list[tuple[date, float]] | None = None,
) -> tuple[list[tuple[date, Decimal]], list[tuple[date, Decimal]]]:
    """(history, projections) as (date, value) pairs.

    With a researched market history (what comparable vehicles sold for, by date), history is that curve
    scaled so it passes through today's value for this vehicle: its condition and miles move it up or down
    the market, the market's shape over time is kept. That covers years before the purchase too.

    History has a point on each 1 January between the purchase and today, plus today, interpolated
    geometrically by elapsed time from the purchase price to today's value (so a June purchase loses half
    a year's value by January, not a whole year's). Without a purchase it is just today's value.
    Projections fall on today's anniversaries, applying the depreciation rate (clamped to 0..60 percent).
    """
    history: list[tuple[date, Decimal]] = []
    market = sorted((d, v) for d, v in (market or []) if v and v > 0)
    if market and market[0][0] < today and current_value > 0:
        factor = current_value / _value_on(market, today)
        history = [(d, _money(v * factor)) for d, v in market if d < today]
    elif purchase_price and purchase_date and purchase_date < today and purchase_price > 0 and current_value > 0:
        span = (today - purchase_date).days
        for year in range(purchase_date.year + 1, today.year + 1):
            d = date(year, 1, 1)
            if purchase_date < d < today:
                frac = (d - purchase_date).days / span
                history.append((d, _money(purchase_price * (current_value / purchase_price) ** frac)))
    history.append((today, _money(current_value)))

    rate = clamp(annual_depreciation_pct, 0.0, 60.0) / 100
    projections = [
        (_anniversary(today, k), _money(current_value * (1 - rate) ** k)) for k in range(1, years_ahead + 1)
    ]
    return history, projections


def _value_on(points: list[tuple[date, float]], day: date) -> float:
    """Linear between the surrounding points; the nearest end point outside them."""
    if day <= points[0][0]:
        return points[0][1]
    for (d0, v0), (d1, v1) in pairwise(points):
        if d0 <= day <= d1:
            return v0 + (v1 - v0) * (day - d0).days / max(1, (d1 - d0).days)
    return points[-1][1]


def store_market_history(db, vehicle: Vehicle, points: list[tuple[date, float]]) -> None:
    """Replace the vehicle's researched market history (source "market"). Does not commit; call
    store_vehicle_valuation afterwards to rebuild the curve from it."""
    from sqlalchemy import delete

    from app.models.asset_value_history import AssetValueHistory

    db.execute(delete(AssetValueHistory).where(AssetValueHistory.vehicle_id == vehicle.id,
                                               AssetValueHistory.source == MARKET))
    for d, v in points:
        db.add(AssetValueHistory(vehicle_id=vehicle.id, date=d, value=_money(v), source=MARKET, is_projected=False))
    db.flush()


def _anniversary(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:   # 29 February
        return d.replace(year=d.year + years, day=28)


def fleet_value_grid(points: dict[str, list[tuple[date, float, bool]]], today: date) -> dict:
    """Every vehicle's value on one shared list of dates, so the series stack.

    A vehicle is 0 before its first point (it was not owned yet; a zero the day before the purchase makes
    the purchase a step, not a ramp), interpolated linearly between its own points, and held at its last
    value after them. Dates after today are projected.
    """
    series = {name: sorted(pts) for name, pts in points.items() if pts}
    grid: set[date] = {d for pts in series.values() for d, _, _ in pts}
    if not grid:
        return {"dates": [], "total": [], "vehicles": {}, "is_projected": []}
    earliest = min(grid)
    grid |= {pts[0][0] - timedelta(days=1) for pts in series.values() if pts[0][0] > earliest}
    dates = sorted(grid)

    def value_on(pts: list[tuple[date, float, bool]], d: date) -> float:
        if d < pts[0][0]:
            return 0.0
        for (d0, v0, _), (d1, v1, _) in pairwise(pts):
            if d0 <= d <= d1:
                return v0 if d1 == d0 else v0 + (v1 - v0) * (d - d0).days / (d1 - d0).days
        return pts[-1][1]

    vehicles = {name: [round(value_on(pts, d), 2) for d in dates] for name, pts in series.items()}
    return {
        "dates": [d.isoformat() for d in dates],
        "total": [round(sum(v[i] for v in vehicles.values()), 2) for i in range(len(dates))],
        "vehicles": vehicles,
        "is_projected": [d > today for d in dates],
    }


def property_projection(
    *, current_value: float, current_year: int, annual_appreciation_pct: float, years_ahead: int = 8
) -> list[tuple[int, Decimal]]:
    rate = clamp(annual_appreciation_pct, -10.0, 15.0) / 100
    return [(current_year + k, _money(current_value * (1 + rate) ** k)) for k in range(1, years_ahead + 1)]


def estimate_vehicle_value(vehicle: Vehicle) -> tuple[VehicleValuation, str]:
    """Ask Claude for today's value; returns (valuation, model id). Raises AIError."""
    description = (
        f"Vehicle: {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim or ''}\n"
        f"Mileage: {vehicle.mileage or 'unknown'} miles\n"
        f"Condition: {vehicle.condition or 'unknown'}\n"
        f"Purchase: {f'${float(vehicle.purchase_price):,.0f}' if vehicle.purchase_price else 'unknown'}"
        f" in {vehicle.purchase_date.year if vehicle.purchase_date else 'unknown year'}\n"
        f"Today: {date.today().isoformat()}"
    )
    valuation = extract(
        VehicleValuation,
        content=description,
        instructions=VEHICLE_INSTRUCTIONS,
        tier="fast",
        max_tokens=1024,
        purpose="vehicle_valuation",
    )
    return valuation, model_for("fast")


def estimate_property_outlook(
    address: str, tax_history: list[dict], current_estimate: float | None, details: dict | None
) -> tuple[PropertyOutlook, str]:
    lines = [f"Address: {address}"]
    for key in ("beds", "baths", "sqft", "year_built", "last_sold_price", "last_sold_date"):
        if details and details.get(key):
            lines.append(f"{key}: {details[key]}")
    for t in sorted(tax_history or [], key=lambda x: x.get("year", 0)):
        if t.get("year") and t.get("assessed_value"):
            lines.append(f"{t['year']} tax assessment: ${t['assessed_value']:,}")
    if current_estimate:
        lines.append(f"{date.today().year} estimate: ${current_estimate:,.0f}")
    outlook = extract(
        PropertyOutlook,
        content="\n".join(lines),
        instructions=PROPERTY_INSTRUCTIONS,
        tier="fast",
        max_tokens=1024,
        purpose="property_outlook",
    )
    return outlook, model_for("fast")


def store_vehicle_valuation(db, vehicle: Vehicle, *, value: float, annual_depreciation_pct: float, reasoning: str,
                            source: str, model: str | None, confidence: str | None, today: date | None = None) -> None:
    """Save a labelled valuation and rebuild the vehicle's computed value curve. Does not commit.

    Rows the owner entered by hand (source "manual") and researched market history (source "market") are
    never touched. History follows the market history when there is one, otherwise it interpolates from
    the purchase to today's value; the purchase is always stored as its own point. Projections apply the
    depreciation rate.
    """
    from datetime import datetime

    from sqlalchemy import delete

    from app.models.asset_value_history import AssetValueHistory

    today = today or date.today()
    vehicle.estimated_value = _money(value)
    vehicle.value_last_updated = datetime.now()
    vehicle.valuation_notes = reasoning
    vehicle.valuation_source = source
    vehicle.valuation_model = model
    vehicle.valuation_confidence = confidence
    market = [(r.date, float(r.value)) for r in db.query(AssetValueHistory).filter(
        AssetValueHistory.vehicle_id == vehicle.id, AssetValueHistory.source == MARKET)]
    history, projections = vehicle_value_curve(
        purchase_price=float(vehicle.purchase_price) if vehicle.purchase_price else None,
        purchase_date=vehicle.purchase_date,
        current_value=float(value),
        today=today,
        annual_depreciation_pct=annual_depreciation_pct,
        market=market,
    )
    db.execute(delete(AssetValueHistory).where(
        AssetValueHistory.vehicle_id == vehicle.id, AssetValueHistory.source.in_(["ai_estimate", "purchase"])))
    db.flush()
    if vehicle.purchase_price and vehicle.purchase_date:
        db.add(AssetValueHistory(vehicle_id=vehicle.id, date=vehicle.purchase_date, value=vehicle.purchase_price,
                                 source="purchase", is_projected=False))
    for d, val in history:
        if vehicle.purchase_date and d == vehicle.purchase_date:
            continue   # the purchase row already marks that day
        db.add(AssetValueHistory(vehicle_id=vehicle.id, date=d, value=val, source="ai_estimate", is_projected=False))
    for d, val in projections:
        db.add(AssetValueHistory(vehicle_id=vehicle.id, date=d, value=val, source="ai_estimate", is_projected=True))
    db.flush()
