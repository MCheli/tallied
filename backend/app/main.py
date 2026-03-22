import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import engine, Base

# Import all models to register them
import app.models  # noqa


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    logger = logging.getLogger("tallied")

    # Safety check: warn if dev mode is active
    if settings.dev_mode:
        db_url = settings.effective_database_url
        local_hosts = ["localhost", "127.0.0.1", "postgres", "tallied-postgres", "db"]
        is_remote_db = not settings.is_sqlite and not any(h in db_url for h in local_hosts)
        if is_remote_db:
            logger.error(
                "SECURITY: Dev mode is enabled but DATABASE_URL points to a remote database. "
                "This is dangerous — dev mode allows password login without Google SSO. "
                "Set FINANCE_DEV_MODE=false for production deployments."
            )
            raise RuntimeError("Dev mode cannot be used with a remote database. Set FINANCE_DEV_MODE=false.")
        logger.warning("Dev mode is ENABLED — local email/password login is available. Disable for production.")

    if not settings.dev_mode and not settings.google_client_id:
        logger.warning("Neither dev mode nor Google SSO is configured. Users will not be able to log in.")

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Tallied API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
from app.api import (  # noqa: E402
    accounts,
    transactions,
    snapshot,
    trends,
    spending,
    income,
    planning,
    import_data,
    mock,
    admin,
    plaid_routes,
    ingest,
    rsu,
    property,
    assets,
    retirement,
    import_unified,
    auth,
)

app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(snapshot.router)
app.include_router(trends.router)
app.include_router(spending.router)
app.include_router(income.router)
app.include_router(planning.router)
app.include_router(import_data.router)
app.include_router(mock.router)
app.include_router(admin.router)
app.include_router(plaid_routes.router)
app.include_router(ingest.router)
app.include_router(rsu.router)
app.include_router(property.router)
app.include_router(assets.router)
app.include_router(retirement.router)
app.include_router(import_unified.router)
app.include_router(auth.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Static file serving (production: serves Vue SPA) ──
STATIC_DIR = Path(__file__).parent.parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve Vue SPA — all non-API routes return index.html."""
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
