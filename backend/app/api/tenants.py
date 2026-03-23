"""Tenant management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import TenantContext, get_tenant_context
from app.models.tenant import Tenant, TenantMembership
from app.services.tenant_service import create_tenant_schema

router = APIRouter(prefix="/tenants", tags=["tenants"])


class CreateTenantRequest(BaseModel):
    display_name: str


@router.get("/")
def list_tenants(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    """List all tenants the current user belongs to."""
    memberships = db.execute(
        select(TenantMembership).where(TenantMembership.user_id == ctx.user_id)
    ).scalars().all()

    tenant_ids = [m.tenant_id for m in memberships]
    if not tenant_ids:
        return []

    tenants = db.execute(
        select(Tenant).where(Tenant.id.in_(tenant_ids)).where(Tenant.is_active.is_(True))
    ).scalars().all()

    return [
        {
            "id": t.id,
            "display_name": t.display_name,
            "slug": t.slug,
            "role": next((m.role for m in memberships if m.tenant_id == t.id), "viewer"),
            "is_default": next((m.is_default for m in memberships if m.tenant_id == t.id), False),
        }
        for t in tenants
    ]


@router.post("/")
def create_tenant(body: CreateTenantRequest, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    """Create a new tenant with the current user as owner."""
    schema_name = Tenant.generate_schema_name()

    tenant = Tenant(
        slug=schema_name,
        display_name=body.display_name,
        schema_name=schema_name,
    )
    db.add(tenant)
    db.flush()

    create_tenant_schema(schema_name)

    db.add(TenantMembership(
        user_id=ctx.user_id,
        tenant_id=tenant.id,
        role="owner",
        is_default=False,
    ))
    db.commit()

    return {
        "id": tenant.id,
        "display_name": tenant.display_name,
        "slug": tenant.slug,
        "schema_name": tenant.schema_name,
    }
