"""Webhook delivery service — signs and POSTs events to subscriber URLs."""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook import WebhookSubscription

logger = logging.getLogger("tallied.webhooks")

MAX_FAILURES = 10
DELIVERY_TIMEOUT = 10  # seconds


def sign_payload(payload: bytes, secret: str) -> str:
    """Create an HMAC-SHA256 signature for the payload."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def deliver_webhook(event_type: str, tenant_id: int, payload: dict, db: Session) -> int:
    """Find all active subscriptions for this tenant+event and POST to their URLs.

    Returns the number of successful deliveries.
    """
    subs = db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.tenant_id == tenant_id,
            WebhookSubscription.is_active.is_(True),
        )
    ).scalars().all()

    matching = [s for s in subs if s.matches_event(event_type)]
    if not matching:
        return 0

    envelope = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    body = json.dumps(envelope, default=str).encode()
    successes = 0

    for sub in matching:
        signature = sign_payload(body, sub.secret)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event_type,
            "X-Webhook-Signature": signature,
        }
        try:
            with httpx.Client(timeout=DELIVERY_TIMEOUT) as client:
                resp = client.post(sub.url, content=body, headers=headers)
                resp.raise_for_status()
            sub.failure_count = 0
            sub.last_delivery = datetime.now(timezone.utc)
            successes += 1
            logger.info("Webhook delivered: event=%s sub=%d url=%s status=%d", event_type, sub.id, sub.url, resp.status_code)
        except Exception as exc:
            sub.failure_count += 1
            logger.warning("Webhook delivery failed: event=%s sub=%d url=%s error=%s failures=%d", event_type, sub.id, sub.url, exc, sub.failure_count)
            if sub.failure_count >= MAX_FAILURES:
                sub.is_active = False
                logger.warning("Webhook subscription %d deactivated after %d consecutive failures", sub.id, MAX_FAILURES)

    db.commit()
    return successes


def send_test_event(sub: WebhookSubscription) -> dict:
    """Send a test event to a single subscription. Returns delivery result."""
    envelope = {
        "event": "test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "This is a test webhook from Tallied.", "subscription_id": sub.id},
    }
    body = json.dumps(envelope, default=str).encode()
    signature = sign_payload(body, sub.secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": "test",
        "X-Webhook-Signature": signature,
    }
    try:
        with httpx.Client(timeout=DELIVERY_TIMEOUT) as client:
            resp = client.post(sub.url, content=body, headers=headers)
            resp.raise_for_status()
        return {"success": True, "status_code": resp.status_code}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
