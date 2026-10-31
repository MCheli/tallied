"""
RSU (Restricted Stock Unit) endpoints.

Provides grant overview, vest schedule, tax lot analysis, and summary data
for the dedicated RSU page and integration with other views.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_tenant_db
from app.models.investment import RSUGrant, VestEvent

router = APIRouter(prefix="/rsu", tags=["rsu"])


def _current_price(db: Session, symbol: str) -> float | None:
    """Get live stock price, cached daily."""
    from app.services.stock_price import get_or_fetch_price
    return get_or_fetch_price(db, symbol)


@router.get("/grants")
def list_grants(db: Session = Depends(get_tenant_db)):
    """All RSU grants with their vest events."""
    grants = db.execute(
        select(RSUGrant).order_by(RSUGrant.grant_date.desc())
    ).scalars().all()

    if not grants:
        return {"grants": [], "current_price": None, "symbol": None}

    symbol = grants[0].symbol or "MSFT"
    price = _current_price(db, symbol)

    result = []
    for g in grants:
        vests = []
        for ve in g.vest_events:
            # Compute tax status: >1 year from vest date = long term
            tax_status = None
            if ve.is_actual and ve.vest_date:
                holding_days = (date.today() - ve.vest_date).days
                tax_status = "Long Term" if holding_days >= 366 else "Short Term"

            # Compute gain/loss per share
            gain_per_share = None
            if ve.fmv_at_vest and price:
                gain_per_share = round(price - float(ve.fmv_at_vest), 2) if price else None

            vests.append({
                "id": ve.id,
                "vest_date": ve.vest_date.isoformat() if ve.vest_date else None,
                "vest_period": ve.vest_period,
                "shares": ve.shares,
                "fmv_at_vest": float(ve.fmv_at_vest) if ve.fmv_at_vest else None,
                "shares_withheld": ve.shares_withheld,
                "shares_released": ve.shares_released,
                "total_taxes_paid": float(ve.total_taxes_paid) if ve.total_taxes_paid else None,
                "is_actual": ve.is_actual,
                "tax_status": tax_status,
                "gain_per_share": gain_per_share,
            })

        held_shares = (g.sellable_shares or 0) + (g.unvested_shares or 0)
        held_value = round(price * held_shares, 2) if price else None

        unvested_value = None
        if price and g.unvested_shares:
            unvested_value = round(price * g.unvested_shares, 2)

        sellable_value = None
        if price and g.sellable_shares:
            sellable_value = round(price * g.sellable_shares, 2)

        result.append({
            "id": g.id,
            "company": g.company,
            "symbol": g.symbol,
            "grant_date": g.grant_date.isoformat() if g.grant_date else None,
            "total_shares": g.total_shares,
            "vested_shares": g.vested_shares,
            "unvested_shares": g.unvested_shares,
            "sellable_shares": g.sellable_shares,
            "held_value": held_value,
            "unvested_value": unvested_value,
            "sellable_value": sellable_value,
            "vest_events": vests,
        })

    return {"grants": result, "current_price": price, "symbol": symbol}


class RSUGrantCreate(BaseModel):
    id: str | None = None
    company: str
    symbol: str | None = None
    grant_date: str | None = None
    total_shares: int | None = None
    vested_shares: int | None = None
    unvested_shares: int | None = None
    sellable_shares: int | None = None


class RSUGrantUpdate(BaseModel):
    company: str | None = None
    symbol: str | None = None
    total_shares: int | None = None
    vested_shares: int | None = None
    unvested_shares: int | None = None
    sellable_shares: int | None = None


@router.get("/grants/{grant_id}")
def get_grant(grant_id: str, db: Session = Depends(get_tenant_db)):
    """Get a single RSU grant by ID."""
    grant = db.get(RSUGrant, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="RSU grant not found")

    symbol = grant.symbol or "MSFT"
    price = _current_price(db, symbol)

    held_shares = (grant.sellable_shares or 0) + (grant.unvested_shares or 0)
    held_value = round(price * held_shares, 2) if price else None

    return {
        "id": grant.id,
        "company": grant.company,
        "symbol": grant.symbol,
        "grant_date": grant.grant_date.isoformat() if grant.grant_date else None,
        "total_shares": grant.total_shares,
        "vested_shares": grant.vested_shares,
        "unvested_shares": grant.unvested_shares,
        "sellable_shares": grant.sellable_shares,
        "held_value": held_value,
        "current_price": price,
    }


@router.post("/grants", status_code=201)
def create_grant(payload: RSUGrantCreate, db: Session = Depends(get_tenant_db)):
    """Create a new RSU grant."""
    import uuid

    grant = RSUGrant(
        id=payload.id or str(uuid.uuid4()),
        company=payload.company,
        symbol=payload.symbol,
        grant_date=date.fromisoformat(payload.grant_date) if payload.grant_date else None,
        total_shares=payload.total_shares,
        vested_shares=payload.vested_shares,
        unvested_shares=payload.unvested_shares,
        sellable_shares=payload.sellable_shares,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return {
        "id": grant.id,
        "company": grant.company,
        "symbol": grant.symbol,
        "grant_date": grant.grant_date.isoformat() if grant.grant_date else None,
        "total_shares": grant.total_shares,
        "vested_shares": grant.vested_shares,
        "unvested_shares": grant.unvested_shares,
        "sellable_shares": grant.sellable_shares,
    }


@router.put("/grants/{grant_id}")
def update_grant(grant_id: str, payload: RSUGrantUpdate, db: Session = Depends(get_tenant_db)):
    """Update an RSU grant's details."""
    grant = db.get(RSUGrant, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="RSU grant not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(grant, key, value)

    db.commit()
    db.refresh(grant)
    return {
        "id": grant.id,
        "company": grant.company,
        "symbol": grant.symbol,
        "grant_date": grant.grant_date.isoformat() if grant.grant_date else None,
        "total_shares": grant.total_shares,
        "vested_shares": grant.vested_shares,
        "unvested_shares": grant.unvested_shares,
        "sellable_shares": grant.sellable_shares,
    }


@router.delete("/grants/{grant_id}", status_code=204)
def delete_grant(grant_id: str, db: Session = Depends(get_tenant_db)):
    """Delete an RSU grant and its vest events."""
    grant = db.get(RSUGrant, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="RSU grant not found")
    # Delete associated vest events first
    for ve in grant.vest_events:
        db.delete(ve)
    db.delete(grant)
    db.commit()
    return None


@router.get("/summary")
def rsu_summary(db: Session = Depends(get_tenant_db)):
    """Aggregate RSU summary for dashboard integration."""
    grants = db.execute(select(RSUGrant)).scalars().all()
    if not grants:
        return {
            "held_shares": 0, "total_granted": 0, "vested_shares": 0, "unvested_shares": 0,
            "sellable_shares": 0, "held_value": 0, "unvested_value": 0,
            "sellable_value": 0, "current_price": None, "symbol": None,
            "upcoming_vests": [], "vesting_income_by_year": {},
        }

    symbol = grants[0].symbol or "MSFT"
    price = _current_price(db, symbol)

    total_shares = sum(g.total_shares or 0 for g in grants)
    vested_shares = sum(g.vested_shares or 0 for g in grants)
    unvested_shares = sum(g.unvested_shares or 0 for g in grants)
    sellable_shares = sum(g.sellable_shares or 0 for g in grants)

    p = price or 0

    # Upcoming vests (future, not yet actual)
    future_vests = db.execute(
        select(VestEvent)
        .where(VestEvent.is_actual.is_(False))
        .order_by(VestEvent.vest_date)
    ).scalars().all()

    upcoming = []
    for ve in future_vests:
        grant = db.get(RSUGrant, ve.grant_id)
        upcoming.append({
            "grant_id": ve.grant_id,
            "grant_date": grant.grant_date.isoformat() if grant and grant.grant_date else None,
            "vest_date": ve.vest_date.isoformat(),
            "shares": ve.shares,
            "est_value": round(p * ve.shares, 2) if p else None,
        })

    # Vesting income by year — actuals use FMV at vest, future uses current price
    all_vests = db.execute(
        select(VestEvent).order_by(VestEvent.vest_date)
    ).scalars().all()

    income_by_year: dict[int, dict] = {}
    for ve in all_vests:
        year = ve.vest_date.year
        entry = income_by_year.setdefault(year, {"actual": 0.0, "projected": 0.0})
        if ve.is_actual:
            if ve.fmv_at_vest and ve.shares:
                entry["actual"] += float(ve.fmv_at_vest) * ve.shares
        else:
            if ve.shares and p:
                entry["projected"] += p * ve.shares

    # Tax lot detail — distribute each grant's sellable shares across vest events
    # using FIFO (oldest vest lots first, which is how E-Trade works)
    # Estimated tax rates for "what would I net" analysis come from settings
    # (FINANCE_LTCG_RATE, FINANCE_STCG_RATE, FINANCE_STATE_TAX_RATE).
    LTCG_RATE = settings.ltcg_rate
    STCG_RATE = settings.stcg_rate
    STATE_RATE = settings.state_tax_rate

    tax_lots: list[dict] = []

    for g in grants:
        remaining_sellable = g.sellable_shares or 0
        if remaining_sellable <= 0:
            continue

        grant_vests = sorted(
            [ve for ve in all_vests if ve.grant_id == g.id and ve.is_actual],
            key=lambda ve: ve.vest_date,
        )

        for ve in grant_vests:
            if remaining_sellable <= 0:
                break
            released = ve.shares_released or 0
            if released <= 0:
                continue

            lot_shares = min(released, remaining_sellable)
            remaining_sellable -= lot_shares

            holding_days = (date.today() - ve.vest_date).days
            is_long = holding_days >= 366
            fmv = float(ve.fmv_at_vest) if ve.fmv_at_vest else 0

            market_value = lot_shares * p
            cost_basis = lot_shares * fmv
            gain = market_value - cost_basis
            tax_rate = (LTCG_RATE if is_long else STCG_RATE) + STATE_RATE
            # Positive gain = tax owed; negative gain = tax benefit (loss offsets other income)
            est_tax = gain * tax_rate
            net_proceeds = market_value - est_tax

            tax_lots.append({
                "grant_id": g.id,
                "grant_date": g.grant_date.isoformat() if g.grant_date else None,
                "vest_date": ve.vest_date.isoformat(),
                "shares": lot_shares,
                "cost_basis_per_share": fmv,
                "current_price": p,
                "market_value": round(market_value, 2),
                "cost_basis": round(cost_basis, 2),
                "gain": round(gain, 2),
                "gain_per_share": round(p - fmv, 2) if (fmv and p) else None,
                "tax_status": "Long Term" if is_long else "Short Term",
                "holding_days": holding_days,
                "est_tax_rate": round(tax_rate, 4),
                "est_tax": round(est_tax, 2),
                "net_proceeds": round(net_proceeds, 2),
            })

    # Aggregate by tax status
    lt_lots = [l for l in tax_lots if l["tax_status"] == "Long Term"]
    st_lots = [l for l in tax_lots if l["tax_status"] == "Short Term"]

    def _agg(lots: list[dict]) -> dict:
        return {
            "shares": sum(l["shares"] for l in lots),
            "market_value": round(sum(l["market_value"] for l in lots), 2),
            "cost_basis": round(sum(l["cost_basis"] for l in lots), 2),
            "gain": round(sum(l["gain"] for l in lots), 2),
            "est_tax": round(sum(l["est_tax"] for l in lots), 2),
            "net_proceeds": round(sum(l["net_proceeds"] for l in lots), 2),
        }

    lt_summary = _agg(lt_lots)
    st_summary = _agg(st_lots)
    all_summary = _agg(tax_lots)
    # Sellable shares that no actual vest lot can account for (grant says sellable,
    # vest events say fewer were released). Surfaced instead of silently dropped.
    unallocated_sellable = max(0, sellable_shares - all_summary["shares"])

    # Current holdings = sellable (held, vested) + unvested (future)
    held_shares = sellable_shares + unvested_shares

    return {
        "held_shares": held_shares,
        "total_granted": total_shares,
        "vested_shares": vested_shares,
        "unvested_shares": unvested_shares,
        "sellable_shares": sellable_shares,
        "held_value": round(p * held_shares, 2),
        "unvested_value": round(p * unvested_shares, 2),
        "sellable_value": round(p * sellable_shares, 2),
        "current_price": price,
        "symbol": symbol,
        "upcoming_vests": upcoming,
        "vesting_income_by_year": {
            str(k): {
                "value": round(v["actual"] + v["projected"], 2),
                "actual": round(v["actual"], 2),
                "projected": round(v["projected"], 2),
                "is_projected": v["projected"] > 0 and v["actual"] == 0,
                "is_mixed": v["projected"] > 0 and v["actual"] > 0,
            }
            for k, v in sorted(income_by_year.items())
        },
        "tax_lots": {
            "long_term": lt_summary,
            "short_term": st_summary,
            "all": all_summary,
            "lots": tax_lots,
            "unallocated_sellable_shares": unallocated_sellable,
            "assumed_rates": {
                "ltcg": LTCG_RATE,
                "stcg": STCG_RATE,
                "state": STATE_RATE,
            },
        },
    }


@router.get("/price-history")
def price_history(symbol: str = "MSFT", range: str = "5y", db: Session = Depends(get_tenant_db)):
    """Closing prices for charting: Yahoo weekly closes (cached six hours) with stored prices taking
    precedence on their days, so the chart agrees with the price used everywhere else."""
    from app.services.stock_price import price_series

    try:
        points = price_series(db, symbol, range)
    except ValueError as e:
        status = 400 if "Invalid" in str(e) else 502
        raise HTTPException(status_code=status, detail=str(e))
    return {"symbol": symbol.upper(), "points": points}
