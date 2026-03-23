"""
401(k) / Retirement account endpoints.

Provides account summary, contribution breakdown, holdings with live prices,
historical balance trend, and statement PDF upload.
"""
import base64
import json
from datetime import date
from decimal import Decimal
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_tenant_db
from app.models.retirement import RetirementAccount, RetirementHolding, RetirementSnapshot
from app.models.import_log import ImportLog

router = APIRouter(prefix="/retirement", tags=["retirement"])


RETIREMENT_PARSE_PROMPT = """You are analyzing a 401(k) / retirement account statement PDF.
Extract the key account details and return them as a JSON object (NOT an array).

Return ONLY valid JSON (no markdown, no explanation):
{
  "plan_name": "plan name",
  "provider": "provider name",
  "statement_start": "YYYY-MM-DD",
  "statement_end": "YYYY-MM-DD",
  "total_balance": 12345.67,
  "vested_balance": 12345.67,
  "account_return_pct": 14.74,
  "return_period_start": "YYYY-MM-DD",
  "roth_balance": 12345.67,
  "pretax_balance": 12345.67,
  "employer_match_balance": 12345.67,
  "other_balance": 0,
  "pretax_deferral_rate_pct": 8,
  "roth_deferral_rate_pct": 2,
  "total_employee_contributions_lifetime": 12345.67,
  "total_employer_contributions_lifetime": 12345.67,
  "roth_basis": 12345.67,
  "estimated_monthly_income": 7976,
  "holdings": [
    {
      "fund_name": "T. Rowe Price Target 2055 TR-G",
      "ticker": "TRRGX",
      "balance": 12345.67,
      "allocation_pct": 100,
      "gain_loss": 9192.09
    }
  ],
  "asset_allocation": {
    "stocks": 94.1,
    "bonds": 2.4,
    "money_market": 2.0,
    "other": 1.5
  },
  "period_contributions": {
    "employee_roth": 715.38,
    "employee_pretax": 2861.52,
    "employer_match": 1073.10
  }
}

For ticker symbols: look up the fund name and provide the ticker if you know it.
For dates: convert to YYYY-MM-DD format.
For percentages in rates: provide as whole numbers (8 not 0.08).
If a field is not found, use null."""


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
    plan_name: Optional[str] = None
    provider: Optional[str] = None
    total_balance: Optional[float] = None
    vested_balance: Optional[float] = None
    roth_balance: Optional[float] = None
    pretax_balance: Optional[float] = None
    employer_match_balance: Optional[float] = None


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
    pretax_deferral_rate: Optional[float] = None  # as decimal, e.g., 0.14
    roth_deferral_rate: Optional[float] = None  # as decimal, e.g., 0.01


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


@router.post("/upload-statement")
def upload_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_tenant_db),
):
    """Parse a 401(k) statement PDF with Claude and import the data."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="FINANCE_ANTHROPIC_API_KEY not configured")

    pdf_bytes = file.file.read()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    title = file.filename or ""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                    {"type": "text", "text": RETIREMENT_PARSE_PROMPT},
                ],
            }],
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    raw_text = message.content[0].text.strip()

    # Parse JSON response (it's an object, not array)
    parsed = None
    try:
        # Strip markdown fences if present
        text = raw_text
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("{"):
            parsed = json.loads(text)
    except json.JSONDecodeError:
        pass

    if not parsed:
        raise HTTPException(status_code=422, detail=f"Could not parse statement. Raw: {raw_text[:500]}")

    # Upsert retirement account
    account = db.execute(
        select(RetirementAccount).limit(1)
    ).scalar_one_or_none()

    if not account:
        account = RetirementAccount(plan_name=parsed.get("plan_name", "401(k)"))
        db.add(account)
        db.flush()

    # Determine if this statement is newer than what we already have
    new_stmt_end = None
    if parsed.get("statement_end"):
        try:
            new_stmt_end = date.fromisoformat(parsed["statement_end"])
        except ValueError:
            pass

    is_newer = (
        new_stmt_end is not None
        and (account.statement_end is None or new_stmt_end >= account.statement_end)
    )

    # Always update plan metadata
    account.plan_name = parsed.get("plan_name") or account.plan_name
    account.provider = parsed.get("provider") or account.provider

    # Only update balances and rates if this statement is newer
    if is_newer:
        account.total_balance = _dec(parsed.get("total_balance")) or account.total_balance
        account.vested_balance = _dec(parsed.get("vested_balance")) or account.vested_balance
        account.roth_balance = _dec(parsed.get("roth_balance")) or account.roth_balance
        account.pretax_balance = _dec(parsed.get("pretax_balance")) or account.pretax_balance
        account.employer_match_balance = _dec(parsed.get("employer_match_balance")) or account.employer_match_balance
        account.other_balance = _dec(parsed.get("other_balance"))

        # Only update deferral rates from newer statements
        if parsed.get("pretax_deferral_rate_pct") is not None:
            account.pretax_deferral_rate = Decimal(str(parsed["pretax_deferral_rate_pct"] / 100))
        if parsed.get("roth_deferral_rate_pct") is not None:
            account.roth_deferral_rate = Decimal(str(parsed["roth_deferral_rate_pct"] / 100))

    # Always update lifetime totals (they only go up)
    new_emp = _dec(parsed.get("total_employee_contributions_lifetime"))
    if new_emp and (not account.total_employee_contributions or new_emp > account.total_employee_contributions):
        account.total_employee_contributions = new_emp
    new_er = _dec(parsed.get("total_employer_contributions_lifetime"))
    if new_er and (not account.total_employer_contributions or new_er > account.total_employer_contributions):
        account.total_employer_contributions = new_er
    new_basis = _dec(parsed.get("roth_basis"))
    if new_basis and (not account.roth_basis or new_basis > account.roth_basis):
        account.roth_basis = new_basis

    if parsed.get("account_return_pct") is not None:
        account.account_return = Decimal(str(parsed["account_return_pct"] / 100))
    if parsed.get("return_period_start"):
        try:
            account.return_period_start = date.fromisoformat(parsed["return_period_start"])
        except ValueError:
            pass

    if parsed.get("statement_start"):
        try:
            account.statement_start = date.fromisoformat(parsed["statement_start"])
        except ValueError:
            pass
    if parsed.get("statement_end"):
        try:
            account.statement_end = date.fromisoformat(parsed["statement_end"])
        except ValueError:
            pass

    account.estimated_monthly_income = _dec(parsed.get("estimated_monthly_income"))

    # Upsert holdings
    for h in parsed.get("holdings", []):
        fund_name = h.get("fund_name", "Unknown")
        existing = db.execute(
            select(RetirementHolding).where(
                RetirementHolding.retirement_account_id == account.id,
                RetirementHolding.fund_name == fund_name,
            )
        ).scalar_one_or_none()

        if existing:
            existing.ticker = h.get("ticker") or existing.ticker
            existing.balance = _dec(h.get("balance"))
            existing.allocation_pct = Decimal(str(h["allocation_pct"] / 100)) if h.get("allocation_pct") else None
            existing.gain_loss = _dec(h.get("gain_loss"))
        else:
            db.add(RetirementHolding(
                retirement_account_id=account.id,
                fund_name=fund_name,
                ticker=h.get("ticker"),
                balance=_dec(h.get("balance")),
                allocation_pct=Decimal(str(h["allocation_pct"] / 100)) if h.get("allocation_pct") else None,
                gain_loss=_dec(h.get("gain_loss")),
            ))

    # Add a balance snapshot for the statement end date
    stmt_end = None
    if parsed.get("statement_end"):
        try:
            stmt_end = date.fromisoformat(parsed["statement_end"])
        except ValueError:
            pass

    if stmt_end and account.total_balance:
        existing_snap = db.execute(
            select(RetirementSnapshot).where(
                RetirementSnapshot.retirement_account_id == account.id,
                RetirementSnapshot.snapshot_date == stmt_end,
            )
        ).scalar_one_or_none()

        if not existing_snap:
            db.add(RetirementSnapshot(
                retirement_account_id=account.id,
                snapshot_date=stmt_end,
                balance=account.total_balance,
                roth_balance=account.roth_balance,
                pretax_balance=account.pretax_balance,
                employer_balance=account.employer_match_balance,
                source="statement",
            ))

    db.add(ImportLog(
        source="retirement_statement",
        capture_mode="pdf",
        status="imported",
        raw_data=json.dumps({"filename": title}),
        parsed_summary=raw_text[:500],
        records_created=1,
    ))
    db.commit()

    return {
        "status": "imported",
        "plan_name": account.plan_name,
        "total_balance": float(account.total_balance) if account.total_balance else None,
        "parsed": parsed,
    }


def _dec(val) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def _fetch_fund_price(ticker: str) -> Optional[float]:
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
