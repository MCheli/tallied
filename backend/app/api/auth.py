"""
Authentication — Google SSO (production) + dev mode login (local development).

Both modes issue JWT tokens that include tenant context (tenant_id + tenant_schema).
The rest of the app resolves tenant from the JWT via get_tenant_context dependency.
"""
from datetime import datetime, timedelta, timezone

import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from jwt import PyJWTError as JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User
from app.services.audit_service import log_event
from app.services.passwords import hash_password, verify_and_upgrade
from app.services.tenant_service import create_tenant_schema

router = APIRouter(prefix="/auth", tags=["auth"])

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 4
REFRESH_TOKEN_EXPIRE_DAYS = 30

# ── OAuth setup ────────────────────────────────────────────────────────────────

oauth = OAuth()
if settings.google_client_id:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# ── Token helpers ──────────────────────────────────────────────────────────────


def _create_token(user_id: int, email: str, tenant_id: int, tenant_schema: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "tenant_id": tenant_id,
            "tenant_schema": tenant_schema,
            "type": "access",
            "exp": expire,
        },
        settings.secret_key, algorithm=ALGORITHM,
    )


def _create_refresh_token(user_id: int) -> str:
    """Create a long-lived refresh token with minimal claims."""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "exp": expire,
        },
        settings.secret_key, algorithm=ALGORITHM,
    )


def _set_auth_cookie(response: Response, token: str, refresh_token: str | None = None):
    response.set_cookie(
        key="tallied_token", value=token,
        httponly=True, samesite="lax", secure=not settings.dev_mode,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )
    if refresh_token:
        response.set_cookie(
            key="tallied_refresh", value=refresh_token,
            httponly=True, samesite="lax", secure=not settings.dev_mode,
            path="/api/v1/auth/refresh",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )


def _resolve_tenant(user: User, db: Session) -> tuple[Tenant, list[Tenant]]:
    """Resolve the user's tenant. Auto-creates one if none exists.

    Returns (active_tenant, all_tenants).
    """
    memberships = db.execute(
        select(TenantMembership).where(TenantMembership.user_id == user.id)
    ).scalars().all()

    if not memberships:
        # Auto-create a default tenant for this user
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
        db.flush()

        return tenant, [tenant]

    # Load all tenants for this user
    tenant_ids = [m.tenant_id for m in memberships]
    tenants = db.execute(
        select(Tenant).where(Tenant.id.in_(tenant_ids)).where(Tenant.is_active.is_(True))
    ).scalars().all()

    if not tenants:
        raise HTTPException(status_code=403, detail="No active tenant for this account")

    # Pick the default tenant, or the first one
    default_membership = next((m for m in memberships if m.is_default), memberships[0])
    active_tenant = next((t for t in tenants if t.id == default_membership.tenant_id), tenants[0])

    return active_tenant, list(tenants)


def _login_response(user: User, tenant: Tenant, tenants: list[Tenant], response: Response) -> dict:
    """Issue JWT with tenant context and return user data."""
    token = _create_token(user.id, user.email, tenant.id, tenant.schema_name)
    refresh_token = _create_refresh_token(user.id)
    _set_auth_cookie(response, token, refresh_token)
    return {
        "user": _serialize_user(user, tenant, tenants),
        "message": "Login successful",
    }


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Extract current user from JWT cookie. Returns None if not authenticated."""
    token = request.cookies.get("tallied_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", 0))
        return db.get(User, user_id)
    except (JWTError, ValueError):
        return None


# ── Google SSO endpoints ───────────────────────────────────────────────────────

@router.get("/google/login")
async def google_login(request: Request):
    """Redirect to Google consent screen."""
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google SSO not configured. Set FINANCE_GOOGLE_CLIENT_ID.")
    redirect_uri = f"{settings.base_url}/api/v1/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, response: Response, db: Session = Depends(get_db)):
    """Handle Google OAuth callback — create/login user, resolve tenant."""
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google SSO not configured")

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {e}")
    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info from Google")

    email = user_info["email"]
    name = user_info.get("name", email.split("@")[0])

    # Find or create user
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        user = User(
            email=email,
            password_hash="",
            display_name=name,
            auth_provider="google",
            status="pending_approval",
        )
        db.add(user)
        db.flush()

    user.last_login = datetime.now(timezone.utc)

    # In dev, redirect to the frontend origin; in prod, "/" works (same origin)
    # In production (not dev mode), redirect to "/" since frontend is same origin.
    # In dev mode, redirect to the frontend dev server (cors_origins[0] = localhost:5173).
    frontend_url = settings.cors_origins[0] if settings.dev_mode and settings.cors_origins else "/"

    # Pending approval users get redirected to the pending page
    if user.status == "pending_approval":
        # Issue a limited JWT (no tenant context) so the frontend can call /auth/me
        expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        pending_token = jwt.encode(
            {
                "sub": str(user.id),
                "email": user.email,
                "exp": expire,
            },
            settings.secret_key, algorithm=ALGORITHM,
        )
        db.commit()
        pending_url = f"{frontend_url}/pending-approval" if frontend_url != "/" else "/pending-approval"
        redirect = RedirectResponse(url=pending_url, status_code=302)
        _set_auth_cookie(redirect, pending_token)
        return redirect

    # Active users get full tenant resolution
    tenant, _tenants = _resolve_tenant(user, db)
    db.commit()

    log_event(
        action="login", resource_type="user", resource_id=str(user.id),
        user_id=user.id, details={"method": "google", "email": email},
        ip_address=request.client.host if request.client else None,
    )

    # Create JWT and redirect to frontend
    jwt_token = _create_token(user.id, user.email, tenant.id, tenant.schema_name)
    refresh_token = _create_refresh_token(user.id)
    redirect = RedirectResponse(url=frontend_url, status_code=302)
    _set_auth_cookie(redirect, jwt_token, refresh_token)
    return redirect


# ── Dev mode login (email/password) ────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def dev_login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Dev mode login with email/password. Only available when FINANCE_DEV_MODE=true."""
    if not settings.dev_mode:
        raise HTTPException(status_code=403, detail="Dev login disabled. Use Google SSO.")

    client_ip = request.client.host if request.client else None
    from app.middleware.rate_limit import login_limiter
    login_limiter.check(f"login:{client_ip or 'unknown'}")
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if not user or not user.password_hash:
        log_event(
            action="login_failed", resource_type="user",
            details={"email": body.email, "reason": "invalid_credentials"},
            ip_address=client_ip,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_and_upgrade(user, body.password):  # rewrites a legacy SHA-256 hash as argon2id
        log_event(
            action="login_failed", resource_type="user", resource_id=str(user.id),
            user_id=user.id, details={"email": body.email, "reason": "wrong_password"},
            ip_address=client_ip,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login = datetime.now(timezone.utc)

    # Resolve tenant
    tenant, tenants = _resolve_tenant(user, db)
    db.commit()

    log_event(
        action="login", resource_type="user", resource_id=str(user.id),
        user_id=user.id, details={"method": "dev_login", "email": body.email},
        ip_address=client_ip,
    )

    return _login_response(user, tenant, tenants, response)


# ── Public demo sign-in ───────────────────────────────────────────────────────

@router.post("/demo")
def demo_login(request: Request, response: Response, db: Session = Depends(get_db)):
    """One-click sign-in as the demo persona. Only when FINANCE_DEMO_MODE=true (app/demo.py)."""
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")
    from app.demo import client_ip
    from app.middleware.rate_limit import login_limiter

    login_limiter.check(f"login:{client_ip(request)}")
    user = db.execute(select(User).where(User.email == settings.demo_user_email)).scalar_one_or_none()
    has_tenant = user is not None and db.execute(
        select(TenantMembership.id).where(TenantMembership.user_id == user.id)).first() is not None
    if not user or not user.is_active or not has_tenant:  # the nightly rebuild is running
        raise HTTPException(status_code=503, detail="The demo is being rebuilt; try again in a minute.")
    tenant, tenants = _resolve_tenant(user, db)
    return _login_response(user, tenant, tenants, response)


# ── Tenant switching ──────────────────────────────────────────────────────────

class SelectTenantRequest(BaseModel):
    tenant_id: int


@router.post("/select-tenant")
def select_tenant(body: SelectTenantRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Switch to a different tenant. Re-issues JWT with new tenant context."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Verify membership
    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == body.tenant_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    tenant = db.get(Tenant, body.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Load all tenants for response
    all_memberships = db.execute(
        select(TenantMembership).where(TenantMembership.user_id == user.id)
    ).scalars().all()
    tenant_ids = [m.tenant_id for m in all_memberships]
    tenants = db.execute(
        select(Tenant).where(Tenant.id.in_(tenant_ids)).where(Tenant.is_active.is_(True))
    ).scalars().all()

    return _login_response(user, tenant, list(tenants), response)


# ── Common endpoints ───────────────────────────────────────────────────────────

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Clear the auth cookies."""
    user = get_current_user(request, db)
    if user:
        log_event(
            action="logout", resource_type="user", resource_id=str(user.id),
            user_id=user.id,
            ip_address=request.client.host if request.client else None,
        )
    response.delete_cookie("tallied_token")
    response.delete_cookie("tallied_refresh", path="/api/v1/auth/refresh")
    return {"message": "Logged out"}


@router.post("/refresh")
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    """Exchange a refresh token for a new access token + refresh token (rotation)."""
    refresh = request.cookies.get("tallied_refresh")
    if not refresh:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(refresh, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.get(User, user_id)
    if not user or not user.is_active or getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Resolve tenant for new access token
    tenant, tenants = _resolve_tenant(user, db)

    # Issue new access + refresh tokens (rotation)
    new_access = _create_token(user.id, user.email, tenant.id, tenant.schema_name)
    new_refresh = _create_refresh_token(user.id)
    _set_auth_cookie(response, new_access, new_refresh)

    return {
        "user": _serialize_user(user, tenant, list(tenants)),
        "authenticated": True,
    }


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    """Get current authenticated user with tenant info."""
    user = get_current_user(request, db)
    if not user:
        return {"user": None, "authenticated": False}

    # Get tenant info from JWT
    token = request.cookies.get("tallied_token")
    current_tenant = None
    tenants = []
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        tenant_id = payload.get("tenant_id")
        if tenant_id:
            current_tenant = db.get(Tenant, int(tenant_id))

            # Load all tenants
            memberships = db.execute(
                select(TenantMembership).where(TenantMembership.user_id == user.id)
            ).scalars().all()
            tenant_ids = [m.tenant_id for m in memberships]
            if tenant_ids:
                tenants = db.execute(
                    select(Tenant).where(Tenant.id.in_(tenant_ids)).where(Tenant.is_active.is_(True))
                ).scalars().all()
    except (JWTError, ValueError):
        pass

    return {
        "user": _serialize_user(user, current_tenant, list(tenants)),
        "authenticated": True,
    }


@router.get("/config")
def auth_config():
    """Tell the frontend what auth methods are available."""
    return {
        "dev_mode": settings.dev_mode,
        "google_sso": bool(settings.google_client_id),
        "demo_mode": settings.demo_mode,
        "demo_url": settings.demo_url or None,
    }


@router.post("/seed-users", include_in_schema=False)
def seed_users(db: Session = Depends(get_db)):
    """Create default dev users with tenants if they don't exist. Only available in dev mode."""
    if not settings.dev_mode:
        raise HTTPException(status_code=403, detail="Seed users only available in dev mode")
    created = []
    defaults = [
        {"email": "claudius@tallied.dev", "password": "demo123", "display_name": "Claudius Banks", "is_admin": False},
        {"email": settings.dev_user_email, "password": settings.dev_user_password, "display_name": "Admin", "is_admin": True},
    ]
    for u in defaults:
        existing = db.execute(select(User).where(User.email == u["email"])).scalar_one_or_none()
        if not existing:
            user = User(
                email=u["email"],
                password_hash=hash_password(u["password"]),
                display_name=u["display_name"],
                is_admin=u["is_admin"],
                auth_provider="local",
            )
            db.add(user)
            db.flush()

            # Auto-create tenant
            _resolve_tenant(user, db)
            created.append(u["email"])

    db.commit()
    return {"created": created}


def _serialize_user(user: User, tenant: Tenant = None, tenants: list | None = None) -> dict:
    result = {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "status": getattr(user, "status", "active"),
    }
    if tenant:
        result["current_tenant"] = {
            "id": tenant.id,
            "display_name": tenant.display_name,
            "slug": tenant.slug,
        }
    if tenants:
        result["tenants"] = [
            {"id": t.id, "display_name": t.display_name, "slug": t.slug}
            for t in tenants
        ]
    return result
