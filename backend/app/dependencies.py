"""Request-scoped dependencies for tenant context and database sessions."""
from dataclasses import dataclass
from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal

ALGORITHM = "HS256"


@dataclass
class TenantContext:
    user_id: int
    email: str
    tenant_id: int
    tenant_schema: str


def get_tenant_context(request: Request) -> TenantContext:
    """Extract tenant context from JWT cookie or API key header.

    Supports two auth methods:
    1. JWT cookie (tallied_token) — set by browser login
    2. X-API-Key header — for programmatic access
    """
    # Try API key first
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return _resolve_api_key(api_key, request)

    # Fall back to JWT cookie
    token = request.cookies.get("tallied_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return TenantContext(
            user_id=int(payload["sub"]),
            email=payload["email"],
            tenant_id=int(payload["tenant_id"]),
            tenant_schema=payload["tenant_schema"],
        )
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


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

        # Update last_used
        api_key.last_used = datetime.now(timezone.utc)
        db.commit()

        return TenantContext(
            user_id=user.id,
            email=user.email,
            tenant_id=tenant.id,
            tenant_schema=tenant.schema_name,
        )
    finally:
        db.close()


def require_admin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    """Verify the authenticated user has admin privileges."""
    from app.models.user import User
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

    The search_path is set via an after_begin event so it is re-applied on
    every new transaction (including after commit + refresh patterns).
    The pool checkout event in database.py resets it to 'public' whenever a
    connection is returned, preventing leaks between requests.
    """
    from sqlalchemy import event
    from app.models.tenant import Tenant

    schema = ctx.tenant_schema

    # SEC-3.2: Validate schema name before interpolating into SQL
    if not Tenant.validate_schema_name(schema):
        raise HTTPException(status_code=400, detail="Invalid tenant schema")

    def _set_search_path(session, transaction, connection):
        connection.execute(text(f'SET search_path TO "{schema}", public'))

    db = SessionLocal()
    event.listen(db, "after_begin", _set_search_path)
    try:
        # Force a connection + transaction so search_path is set immediately
        conn = db.connection()
        conn.execute(text(f'SET search_path TO "{schema}", public'))
        yield db
    finally:
        event.remove(db, "after_begin", _set_search_path)
        try:
            db.rollback()
        except Exception:
            pass
        db.close()
