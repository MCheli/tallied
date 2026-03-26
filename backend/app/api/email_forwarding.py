"""Email forwarding address management — CRUD for registering personal emails."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_context, TenantContext
from app.database import get_db
from app.models.email_forwarding_address import EmailForwardingAddress

router = APIRouter(prefix="/email-forwarding", tags=["email-import"])


class AddEmailRequest(BaseModel):
    email: str


@router.get("")
def list_forwarding_emails(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List registered forwarding email addresses for the current user."""
    addrs = db.execute(
        select(EmailForwardingAddress).where(
            EmailForwardingAddress.user_id == ctx.user_id,
            EmailForwardingAddress.tenant_id == ctx.tenant_id,
        )
    ).scalars().all()
    return [
        {
            "id": a.id,
            "email": a.email,
            "is_active": a.is_active,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in addrs
    ]


@router.post("")
def add_forwarding_email(
    body: AddEmailRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Register a new forwarding email address."""
    email = body.email.lower().strip()

    # Check for duplicates
    existing = db.execute(
        select(EmailForwardingAddress).where(EmailForwardingAddress.email == email)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email address already registered")

    addr = EmailForwardingAddress(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        email=email,
    )
    db.add(addr)
    db.commit()
    db.refresh(addr)
    return {
        "id": addr.id,
        "email": addr.email,
        "is_active": addr.is_active,
        "created_at": addr.created_at.isoformat() if addr.created_at else None,
    }


@router.delete("/{addr_id}")
def delete_forwarding_email(
    addr_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Remove a forwarding email address."""
    addr = db.execute(
        select(EmailForwardingAddress).where(
            EmailForwardingAddress.id == addr_id,
            EmailForwardingAddress.user_id == ctx.user_id,
        )
    ).scalar_one_or_none()
    if not addr:
        raise HTTPException(status_code=404, detail="Email address not found")

    db.delete(addr)
    db.commit()
    return {"status": "deleted"}
