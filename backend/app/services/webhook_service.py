"""Webhook delivery service — signs and POSTs events to subscriber URLs."""
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook import WebhookSubscription

logger = logging.getLogger("tallied.webhooks")

MAX_FAILURES = 10
DELIVERY_TIMEOUT = 10  # seconds
TEST_FAILED = "Delivery failed: the URL did not accept the POST with a 2xx response."


class WebhookTargetError(Exception):
    """The delivery URL does not resolve to a public host."""


def _resolve_public(url: str) -> tuple[str | None, list]:
    """Return (problem, addresses); `problem` is None when every address `url` resolves to is public."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return "Invalid URL", []
    if parsed.scheme not in ("http", "https"):
        return "Webhook URL must start with http:// or https://", []
    host = parsed.hostname
    if not host:
        return "Webhook URL must include a host", []
    if host in ("localhost",) or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        return "Webhook URL must point at a public host", []
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return "Webhook host could not be resolved", []
        addresses = list(dict.fromkeys(ipaddress.ip_address(info[4][0]) for info in infos))
    if not addresses:
        return "Webhook host could not be resolved", []
    for addr in addresses:
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
            return "Webhook URL must point at a public host", []
    return None, addresses


def validate_webhook_url(url: str) -> str | None:
    """Return a problem description, or None when `url` is an acceptable delivery target.

    Accepts http(s) URLs to public hosts only, so the test and delivery POSTs
    cannot be pointed at localhost, the database, or other private services.
    """
    return _resolve_public(url)[0]


def _client() -> httpx.Client:
    return httpx.Client(timeout=DELIVERY_TIMEOUT, follow_redirects=False)


def _post(url: str, body: bytes, headers: dict) -> httpx.Response:
    """POST `body` to `url` at an address checked just now.

    The URL was checked when the subscription was saved, but its DNS can change after that (rebinding).
    So resolve it again, refuse any private address, and connect to the checked IP itself, sending the
    original host as the Host header and the TLS server name so httpx never resolves the name again.
    """
    problem, addresses = _resolve_public(url)
    if problem:
        raise WebhookTargetError(problem)
    parsed = urlparse(url)
    ip = addresses[0]
    ip_host = f"[{ip}]" if ip.version == 6 else str(ip)
    pinned = parsed._replace(netloc=f"{ip_host}:{parsed.port}" if parsed.port else ip_host).geturl()
    headers = {**headers, "Host": parsed.netloc.rsplit("@", 1)[-1]}
    extensions = {"sni_hostname": parsed.hostname} if parsed.scheme == "https" else {}
    with _client() as client:
        resp = client.post(pinned, content=body, headers=headers, extensions=extensions)
        resp.raise_for_status()
        return resp


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
            resp = _post(sub.url, body, headers)
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
        resp = _post(sub.url, body, headers)
        return {"success": True, "status_code": resp.status_code}
    except WebhookTargetError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        # Generic on purpose: refused, timed out and each HTTP status would together map a host's open ports.
        logger.warning("Webhook test failed: sub=%d error=%s", sub.id, exc)
        return {"success": False, "error": TEST_FAILED}


def create_subscription(db: Session, *, user_id: int, tenant_id: int, url: str, events: list[str]) -> WebhookSubscription:
    """Save a new subscription with a fresh signing secret (the caller shows it once)."""
    sub = WebhookSubscription(
        user_id=user_id,
        tenant_id=tenant_id,
        url=url,
        events=",".join(events),
        secret=WebhookSubscription.generate_secret(),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def update_subscription(db: Session, sub: WebhookSubscription, *, url: str | None = None,
                        events: list[str] | None = None, is_active: bool | None = None) -> WebhookSubscription:
    """Apply the given changes; the caller has validated `url` and `events`."""
    if url is not None:
        sub.url = url
    if events is not None:
        sub.events = ",".join(events)
    if is_active is not None:
        sub.is_active = is_active
        if is_active:
            sub.failure_count = 0  # reset on re-activation
    db.commit()
    db.refresh(sub)
    return sub


def delete_subscription(db: Session, sub: WebhookSubscription) -> None:
    db.delete(sub)
    db.commit()
