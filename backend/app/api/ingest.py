"""
Screenshot-based ingest endpoint for the Chrome extension.

Flow:
1. POST /screenshot  — Claude parses image, returns deduplicated findings
                       enriched with current DB value + destination description
2. POST /confirm     — User-approved findings are written to the appropriate tables
"""
import json
from datetime import date
from decimal import Decimal
from typing import Optional

import anthropic
import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.import_log import ImportLog
from app.models.income import W2Record
from app.models.balance import BalanceSnapshot
from app.models.account import Account
from app.models.property import Mortgage

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# ── Prompt ────────────────────────────────────────────────────────────────────

PARSE_PROMPT = """You are analyzing a screenshot of a financial website or document.
Extract financial values and return them as a JSON array.

Rules:
- Each unique financial metric should appear ONCE
- For W2 forms: use the official box labels and skip derived totals that duplicate a box value
- For account pages: return the total account balance, not individual line items that sum to it

Return ONLY a valid JSON array (no markdown, no explanation):
[
  {
    "field": "concise descriptive name",
    "value": "value as displayed",
    "value_numeric": 12345.67,
    "category": "account_balance|income|mortgage|retirement|investment|other",
    "confidence": "high|medium|low",
    "db_field": "one of the values listed below or null"
  }
]

db_field mapping for W2 documents:
- Box 1 wages/tips/other comp → w2_gross_pay  (if you also see a "Gross Pay" line with a higher pre-tax number, prefer that)
- Box 2 federal income tax withheld → w2_federal_tax
- Box 4 social security tax withheld → w2_social_security
- Box 6 medicare tax withheld → w2_medicare
- Box 17 state income tax → w2_state_tax
- Box 12 Code D (401k pretax) → w2_pretax_401k
- Box 12 Code AA (Roth 401k) → w2_roth_401k
- Box 12 Code DD (employer health insurance) → w2_employer_health
- Transportation/transit salary reduction → w2_transit
- Cafeteria/Section 125 deduction → w2_cafeteria_125
- RSU income / stock compensation → w2_rsu_income

db_field for other document types:
- Account or portfolio total balance → account_balance
- Mortgage remaining balance → mortgage_balance

If a field doesn't map to any of the above, use null.
If nothing relevant found, return: []"""

PAYSTUB_PROMPT = """You are analyzing a pay stub / earnings statement PDF.
Extract the YEAR-TO-DATE (YTD) earnings breakdown and key deductions.

IMPORTANT: Use the "year to date" or "total to date" column, NOT the "this period" column.

Return ONLY a valid JSON array (no markdown, no explanation):
[
  {
    "field": "descriptive name",
    "value": "value as displayed",
    "value_numeric": 12345.67,
    "category": "earnings|deduction|tax|benefit|net",
    "confidence": "high|medium|low",
    "db_field": "one of the values listed below or null"
  }
]

db_field mapping for pay stub YTD values:
- Regular pay / base salary YTD → w2_base_salary
- RSU Gain / stock compensation YTD → w2_rsu_income
- Gross Pay YTD → w2_gross_pay
- Federal Income Tax YTD → w2_federal_tax
- Social Security Tax YTD → w2_social_security
- Medicare Tax YTD (combine regular + surtax) → w2_medicare
- State Income Tax YTD → w2_state_tax
- 401K Pre-Tax YTD → w2_pretax_401k
- 401K Roth YTD → w2_roth_401k
- Pretax Park / Transit YTD → w2_transit
- Dental + Medical (combined) → w2_cafeteria_125

Ignore: Retro pay (small adjustments), group term life, MA FLI/MLI, RSU/Net (net settlement amount),
individual period amounts. Focus on YTD totals only.

If nothing relevant found, return: []"""

MORTGAGE_PROMPT = """You are analyzing a mortgage statement PDF.
Extract the key mortgage details and return them as a JSON array.

Return ONLY a valid JSON array (no markdown, no explanation):
[
  {
    "field": "descriptive name",
    "value": "value as displayed",
    "value_numeric": 12345.67,
    "category": "mortgage",
    "confidence": "high|medium|low",
    "db_field": "one of the values listed below or null"
  }
]

db_field mapping:
- Unpaid principal balance / current balance → mortgage_balance
- Interest rate → mortgage_rate
- Monthly payment / total payment due → mortgage_monthly_payment
- Original principal balance → mortgage_original_amount
- Maturity date (as YYYY-MM-DD if possible) → mortgage_maturity_date
- Escrow balance → mortgage_escrow_balance
- Principal portion of payment → mortgage_principal_payment
- Interest portion of payment → mortgage_interest_payment
- Escrow portion of payment → mortgage_escrow_payment

Extract the most recent values. If nothing relevant found, return: []"""

# ── Field metadata: human-readable labels and destination descriptions ────────

# Maps db_field → (human label, W2Record column name)
W2_FIELDS: dict[str, tuple[str, str]] = {
    "w2_gross_pay":       ("Gross Pay",              "gross_pay"),
    "w2_federal_tax":     ("Federal Income Tax",     "federal_tax"),
    "w2_state_tax":       ("State Income Tax",       "state_tax"),
    "w2_social_security": ("Social Security Tax",    "social_security"),
    "w2_medicare":        ("Medicare Tax",           "medicare"),
    "w2_pretax_401k":     ("Pre-Tax 401(k)",         "pretax_401k"),
    "w2_roth_401k":       ("Roth 401(k)",            "roth_401k"),
    "w2_cafeteria_125":   ("Section 125 / Cafeteria","cafeteria_125"),
    "w2_transit":         ("Transit / Commuter",     "transit"),
    "w2_employer_health": ("Employer Health Ins.",   "employer_health"),
    "w2_rsu_income":      ("RSU Income",             "rsu_income"),
    "w2_base_salary":     ("Base Salary",            "base_salary"),
}


# ── Pydantic models ───────────────────────────────────────────────────────────

class ScreenshotRequest(BaseModel):
    image: str
    url: Optional[str] = None
    title: Optional[str] = None


class Finding(BaseModel):
    field: str
    value: str
    value_numeric: Optional[float] = None
    category: str
    confidence: str
    db_field: Optional[str] = None


class ConfirmRequest(BaseModel):
    findings: list[Finding]
    source_url: Optional[str] = None
    # Year hint for W2 data — inferred from page title if not set
    tax_year: Optional[int] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_first_array(text: str) -> Optional[str]:
    """Extract the first complete [...] block by tracking bracket/string depth."""
    depth = 0
    start = None
    in_string = False
    escape_next = False
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i + 1]
    return None


def _deduplicate(findings: list[dict]) -> list[dict]:
    """Keep one entry per db_field and one per (value_numeric, category) group."""
    from collections import defaultdict
    seen_db_fields: set[str] = set()
    conf_order = {"high": 0, "medium": 1, "low": 2}
    groups: dict = defaultdict(list)
    ungrouped = []

    for f in findings:
        vn = f.get("value_numeric")
        cat = f.get("category", "other")
        if vn is not None:
            groups[(round(vn, 2), cat)].append(f)
        else:
            ungrouped.append(f)

    result = []
    for _, group in groups.items():
        with_db = [f for f in group if f.get("db_field") and f["db_field"] != "null"]
        candidates = with_db if with_db else group
        best = min(candidates, key=lambda f: conf_order.get(f.get("confidence", "low"), 2))
        db_f = best.get("db_field") or "null"
        if db_f != "null" and db_f in seen_db_fields:
            continue
        if db_f != "null":
            seen_db_fields.add(db_f)
        result.append(best)

    result.extend(ungrouped)
    return result


def _enrich(findings: list[dict], db: Session, title: Optional[str]) -> list[dict]:
    """
    Add to each finding:
      current_value      — what's in the DB right now for this field
      current_label      — e.g. "2025 W2" or "latest balance"
      destination        — plain English: "2025 W2 Record → Gross Pay"
      action             — "create" | "update" | "append" | "unknown"
    """
    current_year = date.today().year

    # Detect tax year from page title (e.g. "2025 W2 (1).pdf")
    import re
    tax_year = current_year
    if title:
        m = re.search(r"20\d\d", title)
        if m:
            tax_year = int(m.group())

    # Load W2 for that year (or most recent)
    w2 = db.execute(select(W2Record).where(W2Record.tax_year == tax_year)).scalar_one_or_none()
    if not w2:
        w2 = db.execute(select(W2Record).order_by(W2Record.tax_year.desc()).limit(1)).scalar_one_or_none()
    w2_year = w2.tax_year if w2 else tax_year

    # Load latest account balances by display_group
    latest_sub = (
        select(BalanceSnapshot.account_id, sa_func.max(BalanceSnapshot.snapshot_date).label("max_date"))
        .group_by(BalanceSnapshot.account_id).subquery()
    )
    balance_rows = db.execute(
        select(Account.display_group, sa_func.sum(BalanceSnapshot.balance).label("total"))
        .join(latest_sub, Account.id == latest_sub.c.account_id)
        .join(BalanceSnapshot,
              (BalanceSnapshot.account_id == Account.id) &
              (BalanceSnapshot.snapshot_date == latest_sub.c.max_date))
        .group_by(Account.display_group)
    ).all()
    balances = {(dg or "").lower().replace(" ", "_"): float(t) for dg, t in balance_rows if t}

    # Mortgage
    mortgage = db.execute(select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)).scalar_one_or_none()

    enriched = []
    for f in findings:
        db_f = f.get("db_field") or "null"
        current_value = None
        current_label = None
        destination = "Unknown destination"
        action = "unknown"

        if db_f in W2_FIELDS:
            label, col = W2_FIELDS[db_f]
            destination = f"{tax_year} W2 Record → {label}"
            raw = getattr(w2, col, None) if w2 else None
            if raw is not None:
                current_value = float(raw)
                current_label = f"{w2_year} W2"
                action = "update" if w2_year == tax_year else "create"
            else:
                action = "update" if w2 else "create"
                current_label = f"{tax_year} W2" if not w2 else f"{w2_year} W2"

        elif db_f == "account_balance":
            destination = "Balance Snapshot (new snapshot added)"
            action = "append"
            field_lower = f.get("field", "").lower()
            for group, total in balances.items():
                if any(kw in field_lower for kw in group.split("_")):
                    current_value = total
                    current_label = "latest balance"
                    break

        elif db_f == "mortgage_balance":
            destination = "Mortgage Record → Current Balance"
            action = "update" if mortgage else "unknown"
            if mortgage and mortgage.current_balance:
                current_value = float(mortgage.current_balance)
                current_label = "current mortgage"

        else:
            destination = "Not yet mapped to a DB field"
            action = "unknown"

        enriched.append({
            **f,
            "current_value": current_value,
            "current_label": current_label,
            "destination": destination,
            "action": action,
        })

    return enriched


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/screenshot")
def parse_screenshot(body: ScreenshotRequest, db: Session = Depends(get_db)):
    """Parse a screenshot with Claude; return enriched, deduplicated findings."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="FINANCE_ANTHROPIC_API_KEY not configured")

    image_data = body.image
    media_type = "image/png"
    if image_data.startswith("data:"):
        header, image_data = image_data.split(",", 1)
        if "jpeg" in header or "jpg" in header:
            media_type = "image/jpeg"
        elif "webp" in header:
            media_type = "image/webp"

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": PARSE_PROMPT},
                ],
            }],
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    raw_text = message.content[0].text.strip()
    candidate = _extract_first_array(raw_text)
    raw_findings: list[dict] = []
    if candidate:
        try:
            parsed = json.loads(candidate)
            raw_findings = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass

    deduped = _deduplicate(raw_findings)
    enriched = _enrich(deduped, db, body.title)

    db.add(ImportLog(
        source="document_upload",
        capture_mode="screenshot",
        status="parsed",
        raw_data=json.dumps({"url": body.url, "title": body.title}),
        parsed_summary=f"raw={len(raw_findings)} deduped={len(deduped)} | " + raw_text[:300],
        records_created=len(deduped),
    ))
    db.commit()

    return {"findings": enriched, "source_url": body.url}


@router.post("/w2-upload")
def parse_w2_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Parse a W2 PDF with Claude; return enriched findings for confirmation."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="FINANCE_ANTHROPIC_API_KEY not configured")

    # Read and encode the PDF
    pdf_bytes = file.file.read()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    # Detect tax year from filename (e.g. "2024 W2.pdf")
    import re
    title = file.filename or ""
    tax_year_match = re.search(r"20\d\d", title)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": PARSE_PROMPT},
                ],
            }],
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    raw_text = message.content[0].text.strip()
    candidate = _extract_first_array(raw_text)
    raw_findings: list[dict] = []
    if candidate:
        try:
            parsed = json.loads(candidate)
            raw_findings = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass

    deduped = _deduplicate(raw_findings)
    enriched = _enrich(deduped, db, title)

    # Inject detected tax year into findings
    detected_year = int(tax_year_match.group()) if tax_year_match else None

    db.add(ImportLog(
        source="w2_upload",
        capture_mode="pdf",
        status="parsed",
        raw_data=json.dumps({"filename": title}),
        parsed_summary=f"raw={len(raw_findings)} deduped={len(deduped)} | " + raw_text[:300],
        records_created=len(deduped),
    ))
    db.commit()

    return {
        "findings": enriched,
        "filename": title,
        "detected_tax_year": detected_year,
    }


@router.post("/paystub-upload")
def parse_paystub_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Parse a pay stub PDF with Claude; return earnings breakdown for confirmation."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="FINANCE_ANTHROPIC_API_KEY not configured")

    pdf_bytes = file.file.read()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    import re
    title = file.filename or ""
    # Detect year from filename like "Pay Date 2025-12-19.pdf"
    year_match = re.search(r"20\d\d", title)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    },
                    {"type": "text", "text": PAYSTUB_PROMPT},
                ],
            }],
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    raw_text = message.content[0].text.strip()
    candidate = _extract_first_array(raw_text)
    raw_findings: list[dict] = []
    if candidate:
        try:
            parsed = json.loads(candidate)
            raw_findings = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass

    deduped = _deduplicate(raw_findings)

    # Detect tax year: use the year from the pay date in filename
    detected_year = int(year_match.group()) if year_match else None

    enriched = _enrich(deduped, db, title)

    db.add(ImportLog(
        source="paystub_upload",
        capture_mode="pdf",
        status="parsed",
        raw_data=json.dumps({"filename": title}),
        parsed_summary=f"raw={len(raw_findings)} deduped={len(deduped)} | " + raw_text[:300],
        records_created=len(deduped),
    ))
    db.commit()

    return {
        "findings": enriched,
        "filename": title,
        "detected_tax_year": detected_year,
    }


@router.post("/mortgage-upload")
def parse_mortgage_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Parse a mortgage statement PDF with Claude."""
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
                    {"type": "text", "text": MORTGAGE_PROMPT},
                ],
            }],
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    raw_text = message.content[0].text.strip()
    candidate = _extract_first_array(raw_text)
    raw_findings: list[dict] = []
    if candidate:
        try:
            parsed = json.loads(candidate)
            raw_findings = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass

    # Enrich with current mortgage data
    mortgage = db.execute(select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)).scalar_one_or_none()
    enriched = []
    for f in raw_findings:
        current_val = None
        dest = "Not yet mapped"
        if f.get("db_field") == "mortgage_balance" and mortgage:
            current_val = float(mortgage.current_balance) if mortgage.current_balance else None
            dest = "Mortgage → Current Balance"
        elif f.get("db_field") == "mortgage_rate" and mortgage:
            current_val = float(mortgage.rate) if mortgage.rate else None
            dest = "Mortgage → Interest Rate"
        elif f.get("db_field") == "mortgage_monthly_payment" and mortgage:
            current_val = float(mortgage.monthly_payment) if mortgage.monthly_payment else None
            dest = "Mortgage → Monthly Payment"
        elif f.get("db_field") == "mortgage_original_amount" and mortgage:
            current_val = float(mortgage.original_amount) if mortgage.original_amount else None
            dest = "Mortgage → Original Amount"
        elif f.get("db_field"):
            dest = f"Mortgage → {f['field']}"

        enriched.append({
            **f,
            "current_value": current_val,
            "destination": dest,
            "action": "update" if current_val is not None else "create",
        })

    db.add(ImportLog(
        source="mortgage_upload",
        capture_mode="pdf",
        status="parsed",
        raw_data=json.dumps({"filename": title}),
        parsed_summary=f"raw={len(raw_findings)} | " + raw_text[:300],
        records_created=len(raw_findings),
    ))
    db.commit()

    return {"findings": enriched, "filename": title}


@router.post("/confirm")
def confirm_findings(body: ConfirmRequest, db: Session = Depends(get_db)):
    """Write confirmed findings to the appropriate DB tables."""
    if not body.findings:
        return {"saved": 0, "results": []}

    import re
    current_year = date.today().year
    tax_year = body.tax_year or current_year

    # Try to detect tax year from source URL
    if body.source_url:
        m = re.search(r"20\d\d", body.source_url)
        if m:
            tax_year = int(m.group())

    saved = 0
    results = []

    # Bucket findings by destination type
    w2_updates: dict[str, float] = {}
    for f in body.findings:
        db_f = f.db_field or "null"
        if db_f in W2_FIELDS and f.value_numeric is not None:
            _, col = W2_FIELDS[db_f]
            w2_updates[col] = f.value_numeric

    # ── Save W2 fields ────────────────────────────────────────────────────────
    if w2_updates:
        w2 = db.execute(select(W2Record).where(W2Record.tax_year == tax_year)).scalar_one_or_none()
        if w2:
            for col, val in w2_updates.items():
                setattr(w2, col, Decimal(str(val)))
            action = "updated"
        else:
            w2 = W2Record(tax_year=tax_year, **{k: Decimal(str(v)) for k, v in w2_updates.items()})
            db.add(w2)
            action = "created"
        db.flush()
        saved += len(w2_updates)
        results.append({"table": "w2_records", "action": action, "tax_year": tax_year, "fields": list(w2_updates.keys())})

    # ── Save balance snapshots ────────────────────────────────────────────────
    for f in body.findings:
        if (f.db_field or "null") == "account_balance" and f.value_numeric is not None:
            # For now, log it — account matching requires user to map to specific account
            results.append({"table": "balance_snapshots", "action": "pending_account_match",
                           "field": f.field, "value": f.value_numeric,
                           "note": "Balance snapshots require account selection — use Settings to import"})

    # ── Save mortgage fields ─────────────────────────────────────────────────
    MORTGAGE_FIELD_MAP = {
        "mortgage_balance": "current_balance",
        "mortgage_rate": "rate",
        "mortgage_monthly_payment": "monthly_payment",
        "mortgage_original_amount": "original_amount",
    }
    mortgage_updates = {}
    for f in body.findings:
        db_f = f.db_field or "null"
        if db_f in MORTGAGE_FIELD_MAP and f.value_numeric is not None:
            mortgage_updates[MORTGAGE_FIELD_MAP[db_f]] = f.value_numeric

    if mortgage_updates:
        mortgage = db.execute(select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)).scalar_one_or_none()
        if not mortgage:
            mort_acct = db.execute(select(Account).where(Account.account_type == "loan_mortgage").limit(1)).scalar_one_or_none()
            mortgage = Mortgage(account_id=mort_acct.id if mort_acct else None)
            db.add(mortgage)

        for col, val in mortgage_updates.items():
            if col == "rate":
                setattr(mortgage, col, Decimal(str(val / 100 if val > 1 else val)))
            else:
                setattr(mortgage, col, Decimal(str(val)))
        db.flush()
        saved += len(mortgage_updates)
        results.append({"table": "mortgages", "action": "updated", "fields": list(mortgage_updates.keys())})

    db.add(ImportLog(
        source="document_upload",
        capture_mode="screenshot_confirmed",
        status="confirmed",
        records_created=saved,
        raw_data=json.dumps({"source_url": body.source_url, "tax_year": tax_year}),
        parsed_summary=json.dumps(results),
    ))
    db.commit()

    return {"saved": saved, "results": results}
