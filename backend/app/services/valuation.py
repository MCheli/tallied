"""Labelled AI estimates with deterministic projections (AI-3 / DEC-3).

Claude is asked for one number (today's value) plus a rate and reasoning; the
history and projection curves are computed here, so a chart never shows the
model's guesses about the past as fact, and every stored estimate carries its
source, model and confidence.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

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


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _money(value: float) -> Decimal:
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def vehicle_value_curve(
    *,
    purchase_price: float | None,
    purchase_year: int | None,
    current_value: float,
    current_year: int,
    annual_depreciation_pct: float,
    years_ahead: int = 5,
) -> tuple[list[tuple[int, Decimal]], list[tuple[int, Decimal]]]:
    """(history, projections) as (year, value) pairs.

    History interpolates geometrically from the purchase price to today's value
    when both are known; otherwise it is just today's value. Projections apply
    the depreciation rate (clamped to 0..60 percent) from today's value.
    """
    history: list[tuple[int, Decimal]] = []
    if purchase_price and purchase_year and purchase_year < current_year and purchase_price > 0 and current_value > 0:
        span = current_year - purchase_year
        ratio = (current_value / purchase_price) ** (1 / span)
        for i in range(1, span):
            history.append((purchase_year + i, _money(purchase_price * ratio ** i)))
    history.append((current_year, _money(current_value)))

    rate = clamp(annual_depreciation_pct, 0.0, 60.0) / 100
    projections = [
        (current_year + k, _money(current_value * (1 - rate) ** k)) for k in range(1, years_ahead + 1)
    ]
    return history, projections


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
