"""Database credential management endpoints for direct Postgres access."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import TenantContext, get_tenant_context, require_permission
from app.models.db_credential import DbCredential
from app.services.db_credentials import as_utc, issue_credential, list_and_expire, revoke_credential

logger = logging.getLogger("tallied")

router = APIRouter(prefix="/db-credentials", tags=["db-credentials"])

DEFAULT_EXPIRES_DAYS = 90
MAX_EXPIRES_DAYS = 365


class CreateDbCredentialRequest(BaseModel):
    name: str
    access_level: str = "read"  # read, readwrite
    expires_in_days: int = DEFAULT_EXPIRES_DAYS  # 0 = no expiry (max 365)


class DbCredentialResponse(BaseModel):
    id: int
    name: str
    pg_username: str
    access_level: str
    is_active: bool
    created_at: str | None = None
    expires_at: str | None = None


class DbCredentialCreatedResponse(DbCredentialResponse):
    """Returned only on creation -- includes connection details (shown once)."""
    password: str
    host: str
    port: int
    database: str
    schema_name: str
    connection_string: str


def _expires(c: DbCredential) -> str | None:
    return as_utc(c.expires_at).isoformat() if c.expires_at else None


@router.get("/", response_model=list[DbCredentialResponse])
def list_db_credentials(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List all database credentials for the current user's active tenant.

    Automatically revokes expired credentials on read. Postgres also refuses an expired
    credential on its own: each role is created with VALID UNTIL its expiry.
    """
    creds = list_and_expire(db, user_id=ctx.user_id, tenant_id=ctx.tenant_id)
    return [
        DbCredentialResponse(
            id=c.id,
            name=c.name,
            pg_username=c.pg_username,
            access_level=c.access_level,
            is_active=c.is_active,
            created_at=c.created_at.isoformat() if c.created_at else None,
            expires_at=_expires(c),
        )
        for c in creds
    ]


@router.post("/", response_model=DbCredentialCreatedResponse, status_code=201)
def create_db_credential_endpoint(
    body: CreateDbCredentialRequest,
    # A database login outlives the key that made it, so only an admin-level API key may issue one.
    ctx: TenantContext = Depends(require_permission("admin")),
    db: Session = Depends(get_db),
):
    """Create a new database credential. Connection details are returned only once."""
    if body.access_level not in ("read", "readwrite"):
        raise HTTPException(status_code=400, detail="Access level must be 'read' or 'readwrite'")

    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")

    if body.expires_in_days < 0 or body.expires_in_days > MAX_EXPIRES_DAYS:
        raise HTTPException(status_code=400, detail=f"expires_in_days must be 0-{MAX_EXPIRES_DAYS}")

    try:
        credential, result = issue_credential(
            db, user_id=ctx.user_id, tenant_id=ctx.tenant_id, tenant_schema=ctx.tenant_schema,
            name=body.name.strip(), access_level=body.access_level, expires_in_days=body.expires_in_days,
        )
    except Exception as e:
        # Not str(e): a SQLAlchemy error carries the bound parameters, which include the new role's password.
        logger.error("Failed to create database credential: %s: %s", type(e).__name__, getattr(e, "orig", None) or "")
        raise HTTPException(status_code=500, detail="Failed to create database credential")

    return DbCredentialCreatedResponse(
        id=credential.id,
        name=credential.name,
        pg_username=credential.pg_username,
        access_level=credential.access_level,
        is_active=True,
        created_at=credential.created_at.isoformat() if credential.created_at else None,
        expires_at=_expires(credential),
        password=result["password"],
        host=result["host"],
        port=result["port"],
        database=result["database"],
        schema_name=result["schema"],
        connection_string=result["connection_string"],
    )


@router.delete("/{credential_id}")
def revoke_db_credential_endpoint(
    credential_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Revoke a database credential (drops the Postgres role)."""
    credential = db.execute(
        select(DbCredential).where(
            DbCredential.id == credential_id,
            DbCredential.user_id == ctx.user_id,
            DbCredential.tenant_id == ctx.tenant_id,
        )
    ).scalar_one_or_none()

    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    if not credential.is_active:
        raise HTTPException(status_code=400, detail="Credential already revoked")

    revoke_credential(db, credential)
    return {"message": "Database credential revoked"}
