"""Database credential management endpoints for direct Postgres access."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import TenantContext, get_tenant_context
from app.models.db_credential import DbCredential
from app.services.db_credentials import create_db_credential, revoke_db_credential

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


@router.get("/", response_model=list[DbCredentialResponse])
def list_db_credentials(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List all database credentials for the current user's active tenant.

    Automatically revokes expired credentials on read.
    """
    creds = db.execute(
        select(DbCredential).where(
            DbCredential.user_id == ctx.user_id,
            DbCredential.tenant_id == ctx.tenant_id,
        ).order_by(DbCredential.created_at.desc())
    ).scalars().all()

    now = datetime.now(timezone.utc)
    for c in creds:
        if c.is_active and c.expires_at and c.expires_at <= now:
            try:
                revoke_db_credential(c.pg_username)
            except Exception as e:
                logger.error(f"Failed to revoke expired credential {c.pg_username}: {e}")
            c.is_active = False
    db.commit()

    return [
        DbCredentialResponse(
            id=c.id,
            name=c.name,
            pg_username=c.pg_username,
            access_level=c.access_level,
            is_active=c.is_active,
            created_at=c.created_at.isoformat() if c.created_at else None,
            expires_at=c.expires_at.isoformat() if c.expires_at else None,
        )
        for c in creds
    ]


@router.post("/", response_model=DbCredentialCreatedResponse, status_code=201)
def create_db_credential_endpoint(
    body: CreateDbCredentialRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new database credential. Connection details are returned only once."""
    if body.access_level not in ("read", "readwrite"):
        raise HTTPException(status_code=400, detail="Access level must be 'read' or 'readwrite'")

    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")

    if body.expires_in_days < 0 or body.expires_in_days > MAX_EXPIRES_DAYS:
        raise HTTPException(status_code=400, detail=f"expires_in_days must be 0-{MAX_EXPIRES_DAYS}")

    expires_at = None
    if body.expires_in_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    try:
        result = create_db_credential(ctx.tenant_schema, body.access_level)
    except Exception as e:
        logger.error(f"Failed to create database credential: {e}")
        raise HTTPException(status_code=500, detail="Failed to create database credential")

    credential = DbCredential(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        pg_username=result["username"],
        access_level=body.access_level,
        name=body.name.strip(),
        expires_at=expires_at,
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)

    return DbCredentialCreatedResponse(
        id=credential.id,
        name=credential.name,
        pg_username=credential.pg_username,
        access_level=credential.access_level,
        is_active=True,
        created_at=credential.created_at.isoformat() if credential.created_at else None,
        expires_at=credential.expires_at.isoformat() if credential.expires_at else None,
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
        )
    ).scalar_one_or_none()

    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    if not credential.is_active:
        raise HTTPException(status_code=400, detail="Credential already revoked")

    try:
        revoke_db_credential(credential.pg_username)
    except Exception as e:
        logger.error(f"Failed to revoke Postgres role {credential.pg_username}: {e}")
        # Mark as inactive even if role drop fails (role may have been manually removed)

    credential.is_active = False
    db.commit()
    return {"message": "Database credential revoked"}
