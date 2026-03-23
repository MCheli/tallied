import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_tenant_db
from app.models.import_log import ImportLog
from app.schemas.import_data import ImportPayload, ImportResponse, ImportLogResponse
from app.services.import_service import (
    process_import,
    preview_import,
    confirm_import,
    reject_import,
)

router = APIRouter(prefix="/import-legacy", tags=["import-legacy"], include_in_schema=False)
logger = logging.getLogger(__name__)


@router.post("/", response_model=ImportResponse, status_code=201)
def import_data(payload: ImportPayload, db: Session = Depends(get_tenant_db)):
    log = process_import(
        db=db,
        source=payload.source,
        capture_mode=payload.capture_mode,
        raw_data=payload.raw_data,
    )

    parsed_summary = None
    if log.parsed_summary:
        try:
            parsed_summary = json.loads(log.parsed_summary)
        except (json.JSONDecodeError, TypeError):
            parsed_summary = {"raw": log.parsed_summary}

    return ImportResponse(
        import_id=log.id,
        status=log.status,
        records_created=log.records_created,
        parsed_summary=parsed_summary,
    )


@router.post("/preview", status_code=201)
def import_preview(payload: ImportPayload, db: Session = Depends(get_tenant_db)):
    """Parse raw data and return a preview without writing to data tables."""
    try:
        result = preview_import(
            db=db,
            source=payload.source,
            capture_mode=payload.capture_mode,
            raw_data=payload.raw_data,
        )
        return result
    except Exception as e:
        logger.exception("Preview failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{import_id}/confirm")
def import_confirm(import_id: int, db: Session = Depends(get_tenant_db)):
    """Confirm a previewed import — writes parsed records to data tables."""
    try:
        result = confirm_import(db=db, import_id=import_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Confirm import failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{import_id}/reject")
def import_reject(import_id: int, db: Session = Depends(get_tenant_db)):
    """Reject a previewed import — no data written."""
    try:
        result = reject_import(db=db, import_id=import_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Reject import failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log", response_model=list[ImportLogResponse])
def list_import_logs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_tenant_db),
):
    stmt = (
        select(ImportLog)
        .order_by(ImportLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = db.execute(stmt).scalars().all()
    return logs


VISION_PROMPT = """You are a financial data extraction assistant. Analyze this screenshot from a financial website or document.

Extract ALL financial data you can see, including:
- Account names and balances
- Transaction details (date, merchant, amount, category)
- Investment holdings (symbol, shares, value)
- Loan details (balance, rate, payment)
- Income information (salary, bonuses, RSU)

Return the data as a JSON object with these possible top-level keys (include only what you find):
{
  "accounts": [{"name": "...", "balance": 0.00, "type": "checking|savings|credit_card|investment|loan|mortgage"}],
  "transactions": [{"date": "YYYY-MM-DD", "merchant": "...", "amount": -0.00, "category": "..."}],
  "holdings": [{"symbol": "...", "shares": 0, "value": 0.00, "price": 0.00}],
  "balances": [{"account": "...", "balance": 0.00, "date": "YYYY-MM-DD"}],
  "income": {"salary": 0, "rsu": 0, "bonus": 0, "total": 0},
  "summary": "Brief description of what was extracted"
}

Return ONLY valid JSON, no markdown or explanation."""


@router.post("/parse-screenshot")
def parse_screenshot(body: dict, db: Session = Depends(get_tenant_db)):
    """Parse a screenshot using Claude Vision to extract financial data."""
    image_data = body.get("image")
    source = body.get("source", "screenshot")

    if not image_data:
        return {"status": "error", "detail": "No image data provided"}

    log = ImportLog(
        source=source,
        capture_mode="screenshot",
        status="received",
        raw_data=f"[base64 image, {len(str(image_data))} chars]",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    if not settings.anthropic_api_key:
        log.status = "error"
        log.error_message = "Anthropic API key not configured"
        db.commit()
        return {"import_id": log.id, "status": "error", "message": "API key not configured"}

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": VISION_PROMPT,
                        },
                    ],
                }
            ],
        )

        response_text = message.content[0].text

        # Try to parse the JSON response
        try:
            extracted = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                extracted = json.loads(response_text[start:end])
            else:
                extracted = {"raw_text": response_text}

        log.status = "parsed"
        log.parsed_summary = json.dumps(extracted)
        db.commit()

        # Count extracted items
        item_count = sum(
            len(extracted.get(k, []))
            for k in ["accounts", "transactions", "holdings", "balances"]
        )

        return {
            "import_id": log.id,
            "status": "parsed",
            "extracted": extracted,
            "items_found": item_count,
            "summary": extracted.get("summary", "Data extracted from screenshot"),
        }

    except Exception as e:
        logger.exception("Vision parsing failed")
        log.status = "error"
        log.error_message = f"{type(e).__name__}: {e}"
        db.commit()
        return {
            "import_id": log.id,
            "status": "error",
            "message": str(e),
        }
