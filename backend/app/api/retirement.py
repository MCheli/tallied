"""
401(k) / Retirement account endpoints.

Provides account summary, contribution breakdown, holdings with live prices,
historical balance trend, and contribution-rate edits. Statements are imported through the unified import flow.
"""
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db
from app.models.retirement import RetirementAccount, RetirementHolding, RetirementSnapshot

router = APIRouter(prefix="/retirement", tags=["retirement"])


@router.get("/summary")
def retirement_summary(db: Session = Depends(get_tenant_db)):
    """Full retirement account summary."""
    account = db.execute(
        select(RetirementAccount).order_by(RetirementAccount.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    if not account:
        return {"account": None, "holdings": [], "snapshots": [], "asset_allocation": None}

    # Get holdings
    holdings = db.execute(
        select(RetirementHolding)
        .where(RetirementHolding.retirement_account_id == account.id)
    ).scalars().all()

    # Get historical snapshots
    snapshots = db.execute(
        select(RetirementSnapshot)
        .where(RetirementSnapshot.retirement_account_id == account.id)
        .order_by(RetirementSnapshot.snapshot_date)
    ).scalars().all()

    # Fetch live prices for holdings with tickers
    holdings_data = []
    for h in holdings:
        live_price = None
        if h.ticker:
            live_price = _fetch_fund_price(h.ticker)

        holdings_data.append({
            "id": h.id,
            "fund_name": h.fund_name,
            "ticker": h.ticker,
            "balance": float(h.balance) if h.balance else None,
            "allocation_pct": float(h.allocation_pct) if h.allocation_pct else None,
            "gain_loss": float(h.gain_loss) if h.gain_loss else None,
            "live_price": live_price,
        })

    # Compute Roth vs pretax breakdown
    roth = float(account.roth_balance or 0)
    pretax = float(account.pretax_balance or 0)
    employer = float(account.employer_match_balance or 0)
    other = float(account.other_balance or 0)
    total = float(account.total_balance or 0)

    return {
        "account": {
            "id": account.id,
            "plan_name": account.plan_name,
            "provider": account.provider,
            "total_balance": total,
            "vested_balance": float(account.vested_balance or 0),
            "roth_balance": roth,
            "pretax_balance": pretax,
            "employer_match_balance": employer,
            "other_balance": other,
            "pretax_deferral_rate": float(account.pretax_deferral_rate or 0),
            "roth_deferral_rate": float(account.roth_deferral_rate or 0),
            "total_employee_contributions": float(account.total_employee_contributions or 0),
            "total_employer_contributions": float(account.total_employer_contributions or 0),
            "roth_basis": float(account.roth_basis or 0),
            "account_return": float(account.account_return or 0),
            "return_period_start": account.return_period_start.isoformat() if account.return_period_start else None,
            "statement_start": account.statement_start.isoformat() if account.statement_start else None,
            "statement_end": account.statement_end.isoformat() if account.statement_end else None,
            "estimated_monthly_income": float(account.estimated_monthly_income or 0),
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        },
        "balance_breakdown": {
            "roth": roth,
            "pretax": pretax,
            "employer": employer,
            "other": other,
            "roth_pct": round(roth / total * 100, 1) if total > 0 else 0,
            "pretax_pct": round(pretax / total * 100, 1) if total > 0 else 0,
            "employer_pct": round(employer / total * 100, 1) if total > 0 else 0,
        },
        "holdings": holdings_data,
        "snapshots": [
            {
                "date": s.snapshot_date.isoformat(),
                "balance": float(s.balance),
                "roth": float(s.roth_balance) if s.roth_balance else None,
                "pretax": float(s.pretax_balance) if s.pretax_balance else None,
                "employer": float(s.employer_balance) if s.employer_balance else None,
            }
            for s in snapshots
        ],
    }


class RetirementAccountUpdate(BaseModel):
    plan_name: str | None = None
    provider: str | None = None
    total_balance: float | None = None
    vested_balance: float | None = None
    roth_balance: float | None = None
    pretax_balance: float | None = None
    employer_match_balance: float | None = None


@router.put("/account")
def update_retirement_account(body: RetirementAccountUpdate, db: Session = Depends(get_tenant_db)):
    """Update retirement account details (balances, plan info)."""
    account = db.execute(
        select(RetirementAccount).limit(1)
    ).scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="No retirement account found")

    if body.plan_name is not None:
        account.plan_name = body.plan_name
    if body.provider is not None:
        account.provider = body.provider
    if body.total_balance is not None:
        account.total_balance = Decimal(str(body.total_balance))
    if body.vested_balance is not None:
        account.vested_balance = Decimal(str(body.vested_balance))
    if body.roth_balance is not None:
        account.roth_balance = Decimal(str(body.roth_balance))
    if body.pretax_balance is not None:
        account.pretax_balance = Decimal(str(body.pretax_balance))
    if body.employer_match_balance is not None:
        account.employer_match_balance = Decimal(str(body.employer_match_balance))

    db.commit()
    db.refresh(account)
    return {
        "id": account.id,
        "plan_name": account.plan_name,
        "provider": account.provider,
        "total_balance": float(account.total_balance) if account.total_balance else None,
        "vested_balance": float(account.vested_balance) if account.vested_balance else None,
        "roth_balance": float(account.roth_balance) if account.roth_balance else None,
        "pretax_balance": float(account.pretax_balance) if account.pretax_balance else None,
        "employer_match_balance": float(account.employer_match_balance) if account.employer_match_balance else None,
    }


class UpdateRatesRequest(BaseModel):
    pretax_deferral_rate: float | None = None  # as decimal, e.g., 0.14
    roth_deferral_rate: float | None = None  # as decimal, e.g., 0.01


@router.put("/rates")
def update_deferral_rates(body: UpdateRatesRequest, db: Session = Depends(get_tenant_db)):
    """Update contribution deferral rates directly (overrides statement values)."""
    account = db.execute(
        select(RetirementAccount).limit(1)
    ).scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="No retirement account found")

    if body.pretax_deferral_rate is not None:
        account.pretax_deferral_rate = Decimal(str(body.pretax_deferral_rate))
    if body.roth_deferral_rate is not None:
        account.roth_deferral_rate = Decimal(str(body.roth_deferral_rate))

    db.commit()
    return {
        "pretax_deferral_rate": float(account.pretax_deferral_rate or 0),
        "roth_deferral_rate": float(account.roth_deferral_rate or 0),
        "total_deferral_rate": float((account.pretax_deferral_rate or 0) + (account.roth_deferral_rate or 0)),
    }


def _dec(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def _fetch_fund_price(ticker: str) -> float | None:
    """Fetch current fund/ETF price from Yahoo Finance."""
    import urllib.request
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return None
