"""Webhook subscription management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import TenantContext, get_tenant_context
from app.models.webhook import WEBHOOK_EVENTS, WebhookSubscription
from app.services.webhook_service import send_test_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class CreateWebhookRequest(BaseModel):
    url: str
    events: list[str]


class UpdateWebhookRequest(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: int
    url: str
    events: list[str]
    is_active: bool
    created_at: str | None = None
    last_delivery: str | None = None
    failure_count: int


class WebhookCreatedResponse(WebhookResponse):
    """Returned only on creation — includes the signing secret (shown once)."""
    secret: str


def _to_response(sub: WebhookSubscription) -> WebhookResponse:
    return WebhookResponse(
        id=sub.id,
        url=sub.url,
        events=sub.event_list(),
        is_active=sub.is_active,
        created_at=sub.created_at.isoformat() if sub.created_at else None,
        last_delivery=sub.last_delivery.isoformat() if sub.last_delivery else None,
        failure_count=sub.failure_count,
    )


@router.get("/", response_model=list[WebhookResponse])
def list_webhooks(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    """List all webhook subscriptions for the current tenant."""
    subs = db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.user_id == ctx.user_id,
            WebhookSubscription.tenant_id == ctx.tenant_id,
        ).order_by(WebhookSubscription.created_at.desc())
    ).scalars().all()
    return [_to_response(s) for s in subs]


@router.post("/", response_model=WebhookCreatedResponse, status_code=201)
def create_webhook(
    body: CreateWebhookRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new webhook subscription. The signing secret is returned only once."""
    # Validate events
    invalid = [e for e in body.events if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid event types: {', '.join(invalid)}. Valid: {', '.join(WEBHOOK_EVENTS)}")
    if not body.events:
        raise HTTPException(status_code=400, detail="At least one event type is required")

    secret = WebhookSubscription.generate_secret()
    sub = WebhookSubscription(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        url=body.url,
        events=",".join(body.events),
        secret=secret,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    return WebhookCreatedResponse(
        id=sub.id,
        url=sub.url,
        events=sub.event_list(),
        is_active=True,
        created_at=sub.created_at.isoformat() if sub.created_at else None,
        last_delivery=None,
        failure_count=0,
        secret=secret,
    )


@router.put("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    webhook_id: int,
    body: UpdateWebhookRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Update a webhook subscription."""
    sub = db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == ctx.user_id,
            WebhookSubscription.tenant_id == ctx.tenant_id,
        )
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if body.url is not None:
        sub.url = body.url
    if body.events is not None:
        invalid = [e for e in body.events if e not in WEBHOOK_EVENTS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid event types: {', '.join(invalid)}")
        if not body.events:
            raise HTTPException(status_code=400, detail="At least one event type is required")
        sub.events = ",".join(body.events)
    if body.is_active is not None:
        sub.is_active = body.is_active
        if body.is_active:
            sub.failure_count = 0  # reset on re-activation

    db.commit()
    db.refresh(sub)
    return _to_response(sub)


@router.delete("/{webhook_id}")
def delete_webhook(
    webhook_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Delete a webhook subscription."""
    sub = db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == ctx.user_id,
            WebhookSubscription.tenant_id == ctx.tenant_id,
        )
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    db.delete(sub)
    db.commit()
    return {"message": "Webhook deleted"}


@router.post("/{webhook_id}/test")
def test_webhook(
    webhook_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Send a test event to a webhook subscription."""
    sub = db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == ctx.user_id,
            WebhookSubscription.tenant_id == ctx.tenant_id,
        )
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    result = send_test_event(sub)
    return result
