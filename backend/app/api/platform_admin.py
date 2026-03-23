"""Platform admin endpoints for managing users and tenants."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, TenantContext
from app.models.user import User
from app.models.tenant import Tenant, TenantMembership
from app.models.api_key import ApiKey
from app.models.db_credential import DbCredential
from app.services.tenant_service import create_tenant_schema, PLATFORM_TABLES
from app.services.audit_service import log_event

router = APIRouter(prefix="/platform", tags=["platform-admin"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class TenantUpdate(BaseModel):
    display_name: Optional[str] = None
    is_active: Optional[bool] = None


# ── Users ────────────────────────────────────────────────────────────────────


@router.get("/users")
def list_users(
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all platform users with their tenant names."""
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    result = []
    for u in users:
        tenant_rows = db.execute(
            select(Tenant.display_name)
            .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
            .where(TenantMembership.user_id == u.id)
            .order_by(Tenant.display_name)
        ).scalars().all()
        result.append({
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "auth_provider": u.auth_provider,
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "status": getattr(u, "status", "active"),
            "tenant_count": len(tenant_rows),
            "tenants": list(tenant_rows),
        })
    return result


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: int,
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Detailed user info with tenant memberships and key/credential counts."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Tenant memberships with tenant details
    memberships = db.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, TenantMembership.tenant_id == Tenant.id)
        .where(TenantMembership.user_id == user_id)
        .order_by(Tenant.display_name)
    ).all()

    tenant_list = []
    for tm, t in memberships:
        tenant_list.append({
            "tenant_id": t.id,
            "display_name": t.display_name,
            "slug": t.slug,
            "role": tm.role,
            "is_default": tm.is_default,
        })

    api_key_count = db.execute(
        select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user_id)
    ).scalar() or 0

    db_credential_count = db.execute(
        select(func.count()).select_from(DbCredential).where(DbCredential.user_id == user_id)
    ).scalar() or 0

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "auth_provider": user.auth_provider,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "status": getattr(user, "status", "active"),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "tenants": tenant_list,
        "api_key_count": api_key_count,
        "db_credential_count": db_credential_count,
    }


@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: int,
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve a pending user — creates their tenant and sets status to active."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if getattr(user, "status", "active") != "pending_approval":
        raise HTTPException(status_code=400, detail="User is not pending approval")

    # Set status to active
    user.status = "active"

    # Create their tenant (same logic as _resolve_tenant auto-create)
    schema_name = Tenant.generate_schema_name()
    tenant = Tenant(
        slug=schema_name,
        display_name=f"{user.display_name}'s Finances",
        schema_name=schema_name,
    )
    db.add(tenant)
    db.flush()

    create_tenant_schema(schema_name)

    membership = TenantMembership(
        user_id=user.id,
        tenant_id=tenant.id,
        role="owner",
        is_default=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(user)

    log_event(
        action="user_approved", resource_type="user", resource_id=str(user.id),
        user_id=_admin.user_id,
        details={"approved_email": user.email, "tenant_id": tenant.id},
    )
    log_event(
        action="tenant_created", resource_type="tenant", resource_id=str(tenant.id),
        user_id=_admin.user_id,
        details={"schema_name": schema_name, "for_user": user.email},
    )

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "status": user.status,
        "tenant_id": tenant.id,
    }


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user's admin or active status."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    changes = {}
    if body.is_active is not None:
        changes["is_active"] = body.is_active
        user.is_active = body.is_active
    if body.is_admin is not None:
        changes["is_admin"] = body.is_admin
        user.is_admin = body.is_admin
    db.commit()
    db.refresh(user)

    log_event(
        action="admin_action", resource_type="user", resource_id=str(user.id),
        user_id=_admin.user_id,
        details={"action": "update_user", "email": user.email, "changes": changes},
    )

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "status": getattr(user, "status", "active"),
    }


# ── Tenants ──────────────────────────────────────────────────────────────────


@router.get("/tenants")
def list_tenants(
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all tenants with member counts and owner info."""
    tenants = db.execute(select(Tenant).order_by(Tenant.id)).scalars().all()
    result = []
    for t in tenants:
        member_count = db.execute(
            select(func.count()).select_from(TenantMembership).where(
                TenantMembership.tenant_id == t.id
            )
        ).scalar() or 0
        # Find the owner of this tenant
        owner = db.execute(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == t.id,
                TenantMembership.role == "owner",
            )
        ).scalar_one_or_none()
        result.append({
            "id": t.id,
            "display_name": t.display_name,
            "slug": t.slug,
            "schema_name": t.schema_name,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "member_count": member_count,
            "owner_email": owner.email if owner else None,
            "owner_name": owner.display_name if owner else None,
        })
    return result


@router.put("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a tenant's display name or active status."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if body.display_name is not None:
        tenant.display_name = body.display_name
    if body.is_active is not None:
        tenant.is_active = body.is_active
    db.commit()
    db.refresh(tenant)
    return {
        "id": tenant.id,
        "display_name": tenant.display_name,
        "slug": tenant.slug,
        "is_active": tenant.is_active,
    }


@router.get("/tenants/{tenant_id}")
def get_tenant_detail(
    tenant_id: int,
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Detailed tenant info with members and schema table row counts."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Members with user details
    members = db.execute(
        select(TenantMembership, User)
        .join(User, TenantMembership.user_id == User.id)
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(User.display_name)
    ).all()

    member_list = []
    for tm, u in members:
        member_list.append({
            "user_id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "role": tm.role,
            "is_default": tm.is_default,
        })

    # Table row counts from the tenant schema
    table_counts: dict[str, int] = {}
    try:
        # Query information_schema for tables in this tenant's schema
        rows = db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_type = 'BASE TABLE'"
            ),
            {"schema": tenant.schema_name},
        ).fetchall()
        for (table_name,) in rows:
            count = db.execute(
                text(f'SELECT COUNT(*) FROM "{tenant.schema_name}"."{table_name}"')
            ).scalar() or 0
            table_counts[table_name] = count
    except Exception:
        # SQLite or other DB without schema support — skip table counts
        pass

    return {
        "id": tenant.id,
        "display_name": tenant.display_name,
        "slug": tenant.slug,
        "schema_name": tenant.schema_name,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "members": member_list,
        "table_counts": table_counts,
    }


# ── Stats ────────────────────────────────────────────────────────────────────


@router.get("/stats")
def platform_stats(
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """High-level platform statistics."""
    total_users = db.execute(select(func.count()).select_from(User)).scalar() or 0
    active_users = db.execute(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    ).scalar() or 0
    total_tenants = db.execute(select(func.count()).select_from(Tenant)).scalar() or 0
    active_tenants = db.execute(
        select(func.count()).select_from(Tenant).where(Tenant.is_active.is_(True))
    ).scalar() or 0
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
    }


# ── Membership management ───────────────────────────────────────────────────


@router.post("/users/{user_id}/tenants/{tenant_id}")
def add_user_to_tenant(
    user_id: int,
    tenant_id: int,
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add a user to a tenant."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this tenant")

    membership = TenantMembership(user_id=user_id, tenant_id=tenant_id, role="viewer")
    db.add(membership)
    db.commit()
    return {"status": "ok", "user_id": user_id, "tenant_id": tenant_id}


@router.delete("/users/{user_id}/tenants/{tenant_id}")
def remove_user_from_tenant(
    user_id: int,
    tenant_id: int,
    _admin: TenantContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a user from a tenant."""
    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    db.delete(membership)
    db.commit()
    return {"status": "ok", "user_id": user_id, "tenant_id": tenant_id}
