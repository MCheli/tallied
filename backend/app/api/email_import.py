"""Email receipt import — webhook endpoint for Cloudflare Email Worker."""
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.dependencies import get_tenant_db, get_tenant_context, TenantContext
from app.models.email_receipt import EmailReceipt
from app.models.tenant import Tenant
from app.services.email_receipt_service import (
    resolve_forwarding_email,
    parse_receipt_with_ai,
    create_transaction_from_receipt,
)

logger = logging.getLogger("tallied.email_import")

router = APIRouter(prefix="/email-import", tags=["email-import"])


class InboundEmail(BaseModel):
    from_email: str  # Original sender (e.g., order-update@amazon.com)
    forwarded_by: str  # User's personal email that forwarded it
    to: str  # receipts@tallied.dev
    subject: str
    text: str = ""
    html: Optional[str] = None


@router.post("/inbound")
def receive_email(body: InboundEmail, request: Request):
    """Webhook endpoint called by Cloudflare Email Worker when a receipt is forwarded."""
    # Validate webhook secret
    secret = request.headers.get("X-Email-Webhook-Secret", "")
    if not settings.email_webhook_secret or secret != settings.email_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Resolve forwarding email to user/tenant
    db = SessionLocal()
    try:
        fwd = resolve_forwarding_email(body.forwarded_by, db)
        if not fwd:
            logger.warning(f"Unknown forwarding email: {body.forwarded_by}")
            raise HTTPException(status_code=422, detail="Forwarding email not registered")

        tenant = db.get(Tenant, fwd.tenant_id)
        if not tenant or not tenant.is_active:
            raise HTTPException(status_code=422, detail="Tenant not found or inactive")

        schema = tenant.schema_name
        if not Tenant.validate_schema_name(schema):
            raise HTTPException(status_code=400, detail="Invalid tenant schema")
    finally:
        db.close()

    # Open a tenant-scoped session
    def _set_search_path(session, transaction, connection):
        connection.execute(text(f'SET search_path TO "{schema}", public'))

    tenant_db = SessionLocal()
    event.listen(tenant_db, "after_begin", _set_search_path)
    try:
        conn = tenant_db.connection()
        conn.execute(text(f'SET search_path TO "{schema}", public'))

        # Create receipt record
        receipt = EmailReceipt(
            from_email=body.from_email,
            forwarded_by=body.forwarded_by,
            subject=body.subject,
            body_text=body.text,
            body_html=body.html,
            status="received",
        )
        tenant_db.add(receipt)
        tenant_db.flush()

        # Parse with AI
        try:
            email_body = body.text or _strip_html(body.html or "")
            parsed = parse_receipt_with_ai(body.subject, email_body, body.from_email)

            if "error" in parsed:
                receipt.status = "failed"
                receipt.error_message = parsed["error"]
                tenant_db.commit()
                return {"status": "parse_failed", "error": parsed["error"], "receipt_id": receipt.id}

            receipt.parsed_data = json.dumps(parsed)
            txn = create_transaction_from_receipt(tenant_db, parsed, receipt)
            tenant_db.flush()

            receipt.status = "parsed"
            receipt.transaction_id = txn.id
            tenant_db.commit()

            logger.info(f"Created transaction {txn.id} from email receipt {receipt.id} for tenant {schema}")
            return {
                "status": "ok",
                "receipt_id": receipt.id,
                "transaction_id": txn.id,
                "merchant": parsed.get("merchant"),
                "amount": parsed.get("amount"),
            }

        except Exception as e:
            receipt.status = "failed"
            receipt.error_message = str(e)
            tenant_db.commit()
            logger.error(f"Failed to parse email receipt {receipt.id}: {e}")
            return {"status": "parse_failed", "error": str(e), "receipt_id": receipt.id}

    finally:
        event.remove(tenant_db, "after_begin", _set_search_path)
        try:
            tenant_db.rollback()
        except Exception:
            pass
        tenant_db.close()


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
