import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from app.config import settings

# ── Logging config ────────────────────────────────────────────────────────────
# Under gunicorn, app loggers don't propagate to the gunicorn error logger
# unless we explicitly attach a stdout handler. Without this, info-level
# messages from the scheduler and sync routes never reach container
# logs. Configure once at module load — before any logger.getLogger() call
# that needs to emit during startup.
_log_level = os.environ.get("FINANCE_LOG_LEVEL", "INFO").upper()
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
_root = logging.getLogger()
if not any(isinstance(h, logging.StreamHandler) for h in _root.handlers):
    _root.addHandler(_log_handler)
_root.setLevel(_log_level)
for _name in ("tallied", "tallied.sync", "app"):
    logging.getLogger(_name).setLevel(_log_level)

# Damp third-party loggers that flood stdout at INFO.
for _noisy in ("aiohttp", "aiohttp.access", "urllib3", "asyncio"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Import all models to register them
import app.models


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    logger = logging.getLogger("tallied")

    # SEC-1.1: Fail fast if production is running with default secrets
    if not settings.dev_mode and "change-in-production" in settings.secret_key:
        raise RuntimeError("FATAL: FINANCE_SECRET_KEY must be changed from the default before running in production. "
                           "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\"")
    if not settings.dev_mode and "change-in-production" in settings.api_key_pepper:
        raise RuntimeError("FATAL: FINANCE_API_KEY_PEPPER must be changed from the default before running in production. "
                           "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    if not settings.dev_mode and not settings.credential_key.strip():
        raise RuntimeError("FATAL: FINANCE_CREDENTIAL_KEY is required in production (encrypts provider credentials). "
                           "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")

    # SEC-1.3: Guard against dev_mode with a non-local database
    if settings.dev_mode:
        from urllib.parse import urlparse
        parsed = urlparse(settings.database_url)
        if parsed.hostname and parsed.hostname not in ("localhost", "127.0.0.1", "postgres"):
            raise RuntimeError("FATAL: dev_mode=true with non-local database. This looks like production. "
                               "Set FINANCE_DEV_MODE=false.")

    if settings.dev_mode:
        logger.warning(
            "\u26a0\ufe0f  DEV MODE IS ENABLED \u2014 local email/password login is available. "
            "This should NEVER be enabled in production. Set FINANCE_DEV_MODE=false."
        )

    if settings.demo_mode:
        from app.database import SessionLocal
        from app.demo import check_demo_database, check_demo_settings

        check_demo_settings()
        with SessionLocal() as db:
            check_demo_database(db)
        logger.info("DEMO MODE: read-only, one-click sign-in as %s", settings.demo_user_email)
    elif not settings.dev_mode and not settings.google_client_id:
        logger.warning("Neither dev mode nor Google SSO is configured. Users will not be able to log in.")

    # Platform tables are created by Alembic (backend/entrypoint.sh runs
    # `alembic upgrade head` before the server starts; locally `make seed-test`
    # builds and stamps the database). Nothing is created here.

    # APP_ROLE controls whether this process runs the sync scheduler:
    #   - "scheduler" → handled by app/scheduler/__main__.py, NOT here
    #   - "web"       → HTTP only; no scheduler in this process
    #   - unset       → legacy single-container mode (web also runs scheduler)
    # During a rolling deploy from single-container to split-container, infra
    # may not yet set APP_ROLE on the web tier — keep the legacy behavior so
    # nothing breaks until APP_ROLE=web is wired up.
    role = os.environ.get("APP_ROLE", "").lower()
    run_scheduler_in_web = role not in ("web", "scheduler")
    if run_scheduler_in_web:
        from app.services.sync_scheduler import (
            mark_running_jobs_failed,
            reap_stuck_jobs,
            start_scheduler,
            stop_scheduler,
        )
        try:
            reap_stuck_jobs()
        except Exception:
            logger.exception("Watchdog reap_stuck_jobs failed at startup")
        start_scheduler()
    else:
        logger.info("APP_ROLE=%s — scheduler runs in a separate process; web tier will NOTIFY", role)

    yield

    if run_scheduler_in_web:
        # Graceful shutdown — flip any 'running' jobs to 'failed' so the UI
        # doesn't show a 14-min stale "syncing" state until the watchdog
        # fires on the next boot. SIGKILL still skips this.
        try:
            n = mark_running_jobs_failed("worker shutdown")
            if n:
                logger.info("Shutdown: marked %d running sync job(s) as failed", n)
        except Exception:
            logger.exception("Shutdown mark_running_jobs_failed errored")
        stop_scheduler()


# ── Main application ──────────────────────────────────────────────────────────

app = FastAPI(title="Tallied", docs_url=None, redoc_url=None, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.sessions import SessionMiddleware

# SessionMiddleware only on sub-apps (not main app) to avoid duplicate session cookies

# SEC-6.2: Add HSTS header in production to enforce HTTPS
if not settings.dev_mode:
    class HSTSMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return response

    app.add_middleware(HSTSMiddleware)

# ── Import all routers ────────────────────────────────────────────────────────

from app.api import (
    accounts,
    admin,
    api_keys,
    assets,
    auth,
    db_credentials,
    email_forwarding,
    email_import,
    import_unified,
    income,
    planning,
    platform_admin,
    property,
    recap,
    retirement,
    rsu,
    schema,
    simplefin_routes,
    snapshot,
    spending,
    tenants,
    transactions,
    trends,
    webhooks,
)

# ── v1 API (versioned, with OpenAPI docs) ─────────────────────────────────────

v1 = FastAPI(
    title="Tallied API",
    version="1.0.0",
    description="Personal finance data platform API. Authenticate with a JWT cookie (browser) or X-API-Key header (programmatic).",
    openapi_tags=[
        {"name": "accounts", "description": "Financial accounts management"},
        {"name": "transactions", "description": "Transaction history and search"},
        {"name": "snapshot", "description": "Net worth snapshot and summary"},
        {"name": "spending", "description": "Spending analysis by category and trends"},
        {"name": "income", "description": "W2 records and income breakdown"},
        {"name": "rsu", "description": "RSU grants, vesting, and stock prices"},
        {"name": "retirement", "description": "401(k) account summary and holdings"},
        {"name": "property", "description": "Property valuation and mortgage"},
        {"name": "assets", "description": "Vehicle and fixed asset tracking"},
        {"name": "trends", "description": "Historical balance and cash flow trends"},
        {"name": "planning", "description": "Retirement planning scenarios and projections"},
        {"name": "import-v1", "description": "Document import workflow (upload, review, confirm)"},
        {"name": "auth", "description": "Authentication (login, logout, Google SSO)"},
        {"name": "tenants", "description": "Tenant management"},
        {"name": "api-keys", "description": "API key management for programmatic access"},
        {"name": "db-credentials", "description": "Direct database credential management for psql, DBeaver, Excel"},
        {"name": "schema", "description": "Database schema introspection and SQL runner"},
        {"name": "webhooks", "description": "Webhook subscription management for event delivery"},
        {"name": "email-import", "description": "Email receipt import and forwarding address management"},
    ],
)
v1.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=not settings.dev_mode)


# ── Rate-limit response headers middleware ────────────────────────────────────

class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    """Attach X-RateLimit-* headers to every v1 API response.

    The actual enforcement (429 rejection) happens in dependencies.py;
    this middleware only adds informational headers so clients can track
    their remaining quota.
    """

    async def dispatch(self, request: Request, call_next):
        response: StarletteResponse = await call_next(request)

        from app.middleware.rate_limit import rate_limiter

        # Prefer the key stashed by get_tenant_context (exact match with
        # the enforcement bucket).  Fall back to IP-based key.
        rl_key = getattr(request.state, "rate_limit_key", None)
        if not rl_key:
            client = request.client
            rl_key = f"ip:{client.host}" if client else "ip:unknown"

        limit, remaining, reset_ts = rate_limiter.get_usage(rl_key)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response


v1.add_middleware(RateLimitHeaderMiddleware)

from app.demo import DemoReadOnlyMiddleware, NoIndexMiddleware

v1.add_middleware(DemoReadOnlyMiddleware)  # both act only when settings.demo_mode is on
app.add_middleware(NoIndexMiddleware)

from app.middleware.usage_logger import UsageLoggerMiddleware

v1.add_middleware(UsageLoggerMiddleware)

from app.middleware.csrf import OriginCheckMiddleware

v1.add_middleware(OriginCheckMiddleware)  # outermost on v1: a refused cross-origin write runs nothing else

# Financial data routes (tenant-scoped)
v1.include_router(accounts.router)
v1.include_router(transactions.router)
v1.include_router(snapshot.router)
v1.include_router(trends.router)
v1.include_router(spending.router)
v1.include_router(recap.router)
v1.include_router(income.router)
v1.include_router(planning.router)
v1.include_router(import_unified.router)
v1.include_router(simplefin_routes.router)
v1.include_router(rsu.router)
v1.include_router(property.router)
v1.include_router(assets.router)
v1.include_router(retirement.router)

# Admin / schema introspection
v1.include_router(admin.router)
v1.include_router(schema.router)

# Platform routes (public schema)
v1.include_router(auth.router)
v1.include_router(tenants.router)
v1.include_router(api_keys.router)
v1.include_router(db_credentials.router)
v1.include_router(webhooks.router)
v1.include_router(platform_admin.router)
v1.include_router(email_import.router)
v1.include_router(email_forwarding.router)


@v1.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


from fastapi.responses import HTMLResponse


@v1.get("/scalar", response_class=HTMLResponse, include_in_schema=False)
def scalar_docs(dark: str = "0"):
    """Scalar API reference — embedded in the frontend via iframe."""
    is_dark = dark == "1"
    bg = "#030712" if is_dark else "#ffffff"
    return f"""<!DOCTYPE html>
<html><head>
<title>Tallied API Reference</title>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
  body {{ margin: 0; background: {bg}; }}
  /* Hide Scalar top bar and sidebar header for cleaner embed */
  .darklight, .darklight-reference {{ display: none !important; }}
</style>
</head><body>
<script id="api-reference" data-url="./openapi.json"
  data-configuration='{{"theme":"{"saturn" if is_dark else "default"}","layout":"classic","hideDownloadButton":true,"darkMode":{"true" if is_dark else "false"},"hideDarkModeToggle":true}}'></script>
<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.76.4/dist/browser/standalone.js"
  integrity="sha384-hwB9WroDTpZaI38gr+u9CXA6ksz5gUYgD2GxXazKl/agT1L2GWUiRFWGJYNiFu4Q" crossorigin="anonymous"></script>
</body></html>"""


# Mount v1 as a sub-application at /api/v1 (has its own OpenAPI at /api/v1/docs)
app.mount("/api/v1", v1)


# ── Static file serving (production: serves Vue SPA) ──────────────────────────

STATIC_DIR = Path(__file__).parent.parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve Vue SPA — all non-API routes return index.html. An unknown /api path is a JSON 404, not the app."""
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        root = STATIC_DIR.resolve()
        file_path = (root / full_path).resolve()
        if file_path.is_relative_to(root) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(root / "index.html")
