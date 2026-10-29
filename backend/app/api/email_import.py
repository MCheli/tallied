"""Email receipt import — webhook endpoint for the Cloudflare Email Worker.

The webhook stores the receipt and returns at once; parsing (a Claude call)
and the transaction write happen in a background task, so a slow or failing
AI call never blocks the worker and a receipt is never lost (CON-5).
"""
import hmac
import json
import logging
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.dependencies import TenantContext, get_tenant_context, get_tenant_db
from app.models.email_receipt import EmailReceipt
from app.models.tenant import Tenant
from app.services.email_receipt_service import (
    create_transaction_from_receipt,
    parse_receipt_with_ai,
    resolve_forwarding_email,
)
from app.services.tenant_service import tenant_session

logger = logging.getLogger("tallied.email_import")

router = APIRouter(prefix="/email-import", tags=["email-import"])


class InboundEmail(BaseModel):
    from_email: str  # Original sender as seen by the worker (e.g. order-update@amazon.com)
    forwarded_by: str  # SMTP envelope sender: the registered address that forwarded the receipt
    to: str  # receipts@<domain>
    subject: str
    text: str = ""
    html: str | None = None


def _secret_ok(presented: str) -> bool:
    expected = settings.email_webhook_secret
    if not expected:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def process_receipt(schema: str, receipt_id: int) -> None:
    """Parse a stored receipt with Claude and create its transaction. Runs in the background."""
    with tenant_session(schema) as db:
        receipt = db.get(EmailReceipt, receipt_id)
        if receipt is None:
            logger.warning("Receipt %s vanished before processing (%s)", receipt_id, schema)
            return
        try:
            email_body = receipt.body_text or _strip_html(receipt.body_html or "")
            parsed = parse_receipt_with_ai(receipt.subject, email_body, receipt.from_email)
            if "error" in parsed:
                receipt.status = "failed"
                receipt.error_message = parsed["error"]
                db.commit()
                logger.info("Receipt %s not parsed: %s", receipt.id, parsed["error"])
                return
            receipt.parsed_data = json.dumps(parsed)
            txn = create_transaction_from_receipt(db, parsed, receipt)
            db.flush()
            receipt.status = "parsed"
            receipt.transaction_id = txn.id
            db.commit()
            logger.info("Created transaction %s from email receipt %s for tenant %s", txn.id, receipt.id, schema)
        except Exception as e:
            db.rollback()
            receipt = db.get(EmailReceipt, receipt_id)
            if receipt is not None:
                receipt.status = "failed"
                receipt.error_message = str(e)[:2000]
                db.commit()
            logger.exception("Failed to parse email receipt %s", receipt_id)


@router.post("/inbound", status_code=202)
def receive_email(body: InboundEmail, request: Request, background: BackgroundTasks):
    """Webhook called by the Cloudflare Email Worker when a receipt is forwarded.

    The tenant is resolved from `forwarded_by`, which the worker sets from the
    SMTP envelope sender only (never from a From: line inside the body), so a
    receipt lands in a tenant only if it was sent from an address that tenant
    registered on Settings → Email Receipts. Parsing happens after the response.
    """
    if not _secret_ok(request.headers.get("X-Email-Webhook-Secret", "")):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    db = SessionLocal()
    try:
        fwd = resolve_forwarding_email(body.forwarded_by, db)
        if not fwd:
            logger.warning("Receipt from unregistered address rejected: %s", body.forwarded_by)
            raise HTTPException(status_code=422, detail="Forwarding email not registered")
        tenant = db.get(Tenant, fwd.tenant_id)
        if not tenant or not tenant.is_active:
            raise HTTPException(status_code=422, detail="Tenant not found or inactive")
        schema = tenant.schema_name
    finally:
        db.close()

    try:
        session_cm = tenant_session(schema)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant schema")

    with session_cm as tenant_db:
        receipt = EmailReceipt(
            from_email=body.from_email,
            forwarded_by=body.forwarded_by,
            subject=body.subject,
            body_text=body.text,
            body_html=body.html,
            status="received",
        )
        tenant_db.add(receipt)
        tenant_db.commit()
        receipt_id = receipt.id

    background.add_task(process_receipt, schema, receipt_id)
    return {"status": "queued", "receipt_id": receipt_id}


def _strip_html(html: str) -> str:
    """Basic HTML to text conversion."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@router.get("/receipts")
def list_receipts(
    limit: int = 50,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List email receipts for the current tenant."""
    receipts = db.execute(
        select(EmailReceipt).order_by(EmailReceipt.created_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "from_email": r.from_email,
            "subject": r.subject,
            "status": r.status,
            "transaction_id": r.transaction_id,
            "parsed_data": json.loads(r.parsed_data) if r.parsed_data else None,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in receipts
    ]
