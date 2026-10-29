"""Request-scoped dependencies for tenant context and database sessions."""
from dataclasses import dataclass
from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
import jwt
from jwt import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal

ALGORITHM = "HS256"

# API key permission levels, weakest first.
PERMISSION_ORDER = {"read": 0, "write": 1, "admin": 2}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class TenantContext:
    user_id: int
    email: str
    tenant_id: int
    tenant_schema: str
    auth_method: str = "cookie"  # "cookie" | "api_key"
    permissions: str = "admin"  # effective permission level; cookies act as the user


def get_tenant_context(request: Request) -> TenantContext:
    """Extract tenant context from JWT cookie or API key header.

    Supports two auth methods:
    1. JWT cookie (tallied_token) — set by browser login
    2. X-API-Key header — for programmatic access; the key's `permissions`
       decide which HTTP methods it may use (read: safe methods only).
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        ctx = _resolve_api_key(api_key, request)
        if ctx.permissions == "read" and request.method.upper() not in SAFE_METHODS:
            raise HTTPException(status_code=403, detail="This API key is read-only")
        return ctx

    token = request.cookies.get("tallied_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        ctx = TenantContext(
            user_id=int(payload["sub"]),
            email=payload["email"],
            tenant_id=int(payload["tenant_id"]),
            tenant_schema=payload["tenant_schema"],
        )
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    from app.middleware.rate_limit import rate_limiter

    rl_key = f"user:{ctx.user_id}"
    rate_limiter.check(rl_key)
    request.state.rate_limit_key = rl_key
    return ctx


def _resolve_api_key(key: str, request: Request | None = None) -> TenantContext:
    """Validate an API key and return its tenant context."""
    from app.models.api_key import ApiKey
    from app.models.user import User
    from app.models.tenant import Tenant

    key_hash = ApiKey.hash_key(key)
    db = SessionLocal()
    try:
        api_key = db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        ).scalar_one_or_none()

        if not api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Rate-limit per API key
        from app.middleware.rate_limit import rate_limiter
        rl_key = f"apikey:{api_key.id}"
        rate_limiter.check(rl_key)

        # Stash key on request.state so the header middleware can read it
        if request is not None:
            request.state.rate_limit_key = rl_key

        user = db.get(User, api_key.user_id)
        tenant = db.get(Tenant, api_key.tenant_id)
        if not user or not tenant or not tenant.is_active:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if not user.is_active or getattr(user, "status", "active") != "active":
            raise HTTPException(status_code=401, detail="User is not active")

        # Update last_used
        api_key.last_used = datetime.now(timezone.utc)
        db.commit()

        permissions = api_key.permissions if api_key.permissions in PERMISSION_ORDER else "read"
        return TenantContext(
            user_id=user.id,
            email=user.email,
            tenant_id=tenant.id,
            tenant_schema=tenant.schema_name,
            auth_method="api_key",
            permissions=permissions,
        )
    finally:
        db.close()


def require_permission(level: str):
    """Dependency factory: require at least `level` ("read" | "write" | "admin").

    Cookie sessions act as the user and always pass. API keys pass when their
    stored permission level is at least `level`.
    """
    needed = PERMISSION_ORDER[level]

    def _check(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.auth_method == "api_key" and PERMISSION_ORDER.get(ctx.permissions, 0) < needed:
            raise HTTPException(status_code=403, detail=f"This API key does not have {level} permission")
        return ctx

    return _check


def require_admin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    """Verify the authenticated user has admin privileges (and, for API keys, an admin-level key)."""
    from app.models.user import User

    if ctx.auth_method == "api_key" and ctx.permissions != "admin":
        raise HTTPException(status_code=403, detail="Admin API key required")
    db = SessionLocal()
    try:
        user = db.get(User, ctx.user_id)
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        return ctx
    finally:
        db.close()


def get_tenant_db(
    ctx: TenantContext = Depends(get_tenant_context),
) -> Generator[Session, None, None]:
    """Provide a DB session scoped to the authenticated tenant's schema.

    Delegates to `tenant_service.tenant_session`, which re-applies the
    search_path on every new transaction (the pool checkout event in
    database.py resets it to 'public' whenever a connection is returned).
    """
    from app.services.tenant_service import tenant_session

    try:
        with tenant_session(ctx.tenant_schema) as db:
            yield db
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant schema")
