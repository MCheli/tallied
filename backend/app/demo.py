"""Public demo mode (FINANCE_DEMO_MODE=true): money-demo.markcheli.com.

The demo is its own deployment with its own database holding only the Claudius Banks seed, rebuilt
nightly. Anyone may look; nobody may change anything. Three layers keep it that way:

1. `DemoReadOnlyMiddleware` refuses every POST/PUT/PATCH/DELETE except `ALLOWED_WRITES`
   (signing in and out, and calculations that save nothing).
2. Tenant sessions run in READ ONLY transactions (`get_tenant_db`), so a write that slipped past
   the middleware still fails in Postgres.
3. `check_demo_database` refuses to start if the database holds any account that is not a demo
   persona, so the demo can never be pointed at real data, and startup refuses AI and SSO secrets.
"""
from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
DEMO_EMAIL_DOMAIN = "@tallied.dev"
READ_ONLY_DETAIL = "This is the public demo with made-up data, so nothing can be changed or saved."

# Paths inside /api/v1. Everything else that writes is refused.
ALLOWED_WRITES = [
    re.compile(r"^/auth/(demo|logout|refresh)$"),
    re.compile(r"^/plans/\d+/(what-if|sprint)$"),  # outlook with levers changed; writes nothing
    re.compile(r"^/admin/query$"),  # the SQL runner: read-only transaction, tenant schema only
]


def write_allowed(method: str, path: str) -> bool:
    if method.upper() in SAFE_METHODS:
        return True
    path = path.removeprefix("/api/v1")
    return any(p.match(path) for p in ALLOWED_WRITES)


class DemoReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.demo_mode and not write_allowed(request.method, request.url.path):
            return JSONResponse({"detail": READ_ONLY_DETAIL, "demo": True}, status_code=403)
        return await call_next(request)


class NoIndexMiddleware(BaseHTTPMiddleware):
    """The demo is linked from the owner's site but should not be indexed as if it were a product."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if settings.demo_mode:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response


def client_ip(request: Request) -> str:
    """The visitor's address. Cloudflare sets CF-Connecting-IP; NGINX passes it through."""
    return request.headers.get("CF-Connecting-IP") or (request.client.host if request.client else "unknown")


def check_demo_settings() -> None:
    if settings.anthropic_api_key.strip():
        raise RuntimeError("FATAL: demo mode must not have FINANCE_ANTHROPIC_API_KEY (AI features are off in the demo).")
    if settings.google_client_id.strip():
        raise RuntimeError("FATAL: demo mode must not have Google SSO configured; visitors sign in as the demo persona.")
    if not settings.demo_user_email.endswith(DEMO_EMAIL_DOMAIN):
        raise RuntimeError(f"FATAL: FINANCE_DEMO_USER_EMAIL must be a {DEMO_EMAIL_DOMAIN} persona.")


def check_demo_database(db: Session) -> None:
    """Refuse to serve a database that holds anyone but demo personas (i.e. a real one)."""
    from app.models.user import User

    real = db.execute(select(User.id).where(~User.email.endswith(DEMO_EMAIL_DOMAIN)).limit(1)).first()
    if real is not None:
        raise RuntimeError("FATAL: demo mode is pointed at a database with real users. "
                           "The demo must run on its own database holding only the seed.")
