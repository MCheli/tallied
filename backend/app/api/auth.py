"""Authentication endpoints — JWT-based login."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from jose import jwt, JWTError
import hashlib

from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Config — in production, use env var for SECRET_KEY
SECRET_KEY = "tallied-dev-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

def _hash_password(password: str) -> str:
    """Simple SHA-256 hash. Use bcrypt in production."""
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(plain: str, hashed: str) -> bool:
    return _hash_password(plain) == hashed


def _create_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "email": email, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Extract current user from JWT cookie. Returns None if not authenticated."""
    token = request.cookies.get("tallied_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", 0))
        return db.get(User, user_id)
    except (JWTError, ValueError):
        return None


# ── Endpoints ──

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Login with email/password. Sets JWT cookie."""
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = _create_token(user.id, user.email)
    user.last_login = datetime.utcnow()
    db.commit()

    response.set_cookie(
        key="tallied_token", value=token,
        httponly=True, samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )

    return {
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name, "is_admin": user.is_admin},
        "message": "Login successful",
    }


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
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name, "is_admin": user.is_admin},
        "authenticated": True,
    }


@router.post("/seed-users")
def seed_users(db: Session = Depends(get_db)):
    """Create default users if they don't exist. Called on first run."""
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
            ))
            created.append(u["email"])

    db.commit()
    return {"created": created, "message": f"Created {len(created)} users"}
