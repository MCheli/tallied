"""
Authentication — Google SSO (production) + dev mode login (local development).

Production: Google OIDC via Authlib. User clicks "Sign in with Google",
redirected to Google consent, comes back with identity token → JWT.

Dev mode (FINANCE_DEV_MODE=true): Simple email/password login for test users.
No Google account needed. Enabled by default for local development.

Both modes issue the same JWT token, so the rest of the app doesn't care
how the user authenticated.
"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.config import settings
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

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


def _create_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "exp": expire},
        settings.secret_key, algorithm=ALGORITHM,
    )


def _set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key="tallied_token", value=token,
        httponly=True, samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
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
    redirect_uri = f"{settings.base_url}/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback — create/login user."""
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google SSO not configured")

    token = await oauth.google.authorize_access_token(request)
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
            password_hash="",  # No password for SSO users
            display_name=name,
            auth_provider="google",
        )
        db.add(user)
        db.flush()

    user.last_login = datetime.utcnow()
    db.commit()

    # Create JWT and redirect to frontend
    jwt_token = _create_token(user.id, user.email)
    response = RedirectResponse(url="/", status_code=302)
    _set_auth_cookie(response, jwt_token)
    return response


# ── Dev mode login (email/password) ────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def dev_login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Dev mode login with email/password. Only available when FINANCE_DEV_MODE=true."""
    if not settings.dev_mode:
        raise HTTPException(status_code=403, detail="Dev login disabled. Use Google SSO.")

    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if not user or not user.password_hash or _hash_password(body.password) != user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login = datetime.utcnow()
    db.commit()

    token = _create_token(user.id, user.email)
    _set_auth_cookie(response, token)

    return {
        "user": _serialize_user(user),
        "message": "Login successful",
    }


# ── Common endpoints ───────────────────────────────────────────────────────────

@router.post("/logout")
def logout(response: Response):
    """Clear the auth cookie."""
    response.delete_cookie("tallied_token")
    return {"message": "Logged out"}


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    """Get current authenticated user."""
    user = get_current_user(request, db)
    if not user:
        return {"user": None, "authenticated": False}
    return {
        "user": _serialize_user(user),
        "authenticated": True,
    }


@router.get("/config")
def auth_config():
    """Tell the frontend what auth methods are available."""
    return {
        "dev_mode": settings.dev_mode,
        "google_sso": bool(settings.google_client_id),
    }


@router.post("/seed-users")
def seed_users(db: Session = Depends(get_db)):
    """Create default dev users if they don't exist."""
    created = []
    defaults = [
        {"email": "claudius@tallied.dev", "password": "demo123", "display_name": "Claudius Banks", "is_admin": False},
        {"email": "admin@tallied.dev", "password": "admin123", "display_name": "Admin", "is_admin": True},
    ]
    for u in defaults:
        existing = db.execute(select(User).where(User.email == u["email"])).scalar_one_or_none()
        if not existing:
            db.add(User(
                email=u["email"],
                password_hash=_hash_password(u["password"]),
                display_name=u["display_name"],
                is_admin=u["is_admin"],
                auth_provider="local",
            ))
            created.append(u["email"])
    db.commit()
    return {"created": created}


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
    }
