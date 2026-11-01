"""Service for managing Postgres roles for tenant direct access."""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine
from app.models.db_credential import DbCredential

logger = logging.getLogger("tallied")

# Each tld_* role may hold this many connections at once (psql, DBeaver and Excel open one or two each).
CONNECTION_LIMIT = 5


def _parse_db_host_port() -> tuple[str, int, str]:
    """Extract public-facing host, port, database for user connection strings.

    Uses FINANCE_DB_PUBLIC_HOST / FINANCE_DB_PUBLIC_PORT when set (production),
    otherwise falls back to the values in FINANCE_DATABASE_URL (local dev).
    """
    from urllib.parse import urlparse
    parsed = urlparse(settings.database_url)
    host = settings.db_public_host or parsed.hostname or "localhost"
    port = settings.db_public_port or parsed.port or 5432
    database = (parsed.path or "/tallied").lstrip("/")
    return host, port, database


def create_db_credential(tenant_schema: str, access_level: str = "read", expires_at: datetime | None = None) -> dict:
    """Create a Postgres role with access to the tenant schema.

    With `expires_at`, the role carries VALID UNTIL, so Postgres itself refuses the password after that
    time even if nobody lists or revokes the credential.

    Returns: {username, password, host, port, database, schema, connection_string}
    """
    username = f"tld_{tenant_schema[:20]}_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    host, port, database = _parse_db_host_port()

    with engine.connect() as conn:
        # Create role with login, a connection cap and (when set) an expiry
        valid_until = " VALID UNTIL :until" if expires_at else ""
        params = {"pw": password}
        if expires_at:
            params["until"] = expires_at.astimezone(timezone.utc).isoformat()
        conn.execute(
            text(f'CREATE ROLE "{username}" LOGIN PASSWORD :pw CONNECTION LIMIT {CONNECTION_LIMIT}{valid_until}'),
            params,
        )

        # SECURITY: Lock down the role
        # Revoke default public schema access
        conn.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{username}"'))
        conn.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{username}"'))
        # Lock search_path to only the tenant schema (hides other schemas in \dn)
        conn.execute(text(f'ALTER ROLE "{username}" SET search_path TO "{tenant_schema}"'))

        # Grant access ONLY to the specific tenant schema
        conn.execute(text(f'GRANT USAGE ON SCHEMA "{tenant_schema}" TO "{username}"'))
        if access_level == "readwrite":
            conn.execute(
                text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{tenant_schema}" TO "{username}"')
            )
            conn.execute(
                text(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{tenant_schema}" '
                    f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{username}"'
                )
            )
        else:
            conn.execute(
                text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{tenant_schema}" TO "{username}"')
            )
            conn.execute(
                text(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{tenant_schema}" '
                    f'GRANT SELECT ON TABLES TO "{username}"'
                )
            )
        conn.commit()

    connection_string = (
        f"postgresql://{username}:{password}@{host}:{port}/{database}"
        f"?options=-csearch_path%3D{tenant_schema}"
    )

    return {
        "username": username,
        "password": password,  # only returned on creation
        "host": host,
        "port": port,
        "database": database,
        "schema": tenant_schema,
        "connection_string": connection_string,
    }


def revoke_db_credential(username: str) -> None:
    """Drop a Postgres role, revoking all access."""
    with engine.connect() as conn:
        # Revoke all privileges first to avoid "role cannot be dropped" errors
        conn.execute(text(f'REASSIGN OWNED BY "{username}" TO tallied'))
        conn.execute(text(f'DROP OWNED BY "{username}"'))
        conn.execute(text(f'DROP ROLE IF EXISTS "{username}"'))
        conn.commit()
    logger.info(f"Revoked database credential: {username}")


def as_utc(value: datetime) -> datetime:
    # expires_at is a naive column: Postgres hands back what was written, without its offset (UTC).
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def issue_credential(db: Session, *, user_id: int, tenant_id: int, tenant_schema: str,
                     name: str, access_level: str, expires_in_days: int) -> tuple[DbCredential, dict]:
    """Create the Postgres role and its platform row. Returns (row, connection details incl. password)."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days) if expires_in_days > 0 else None
    result = create_db_credential(tenant_schema, access_level, expires_at)
    credential = DbCredential(
        user_id=user_id,
        tenant_id=tenant_id,
        pg_username=result["username"],
        access_level=access_level,
        name=name,
        expires_at=expires_at.replace(tzinfo=None) if expires_at else None,
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential, result


def list_and_expire(db: Session, *, user_id: int, tenant_id: int) -> list[DbCredential]:
    """The user's credentials for the tenant, newest first, dropping the roles of any that have expired."""
    creds = db.execute(
        select(DbCredential).where(
            DbCredential.user_id == user_id,
            DbCredential.tenant_id == tenant_id,
        ).order_by(DbCredential.created_at.desc())
    ).scalars().all()

    now = datetime.now(timezone.utc)
    for c in creds:
        if c.is_active and c.expires_at and as_utc(c.expires_at) <= now:
            try:
                revoke_db_credential(c.pg_username)
            except Exception as e:
                logger.error(f"Failed to revoke expired credential {c.pg_username}: {e}")
            c.is_active = False
    db.commit()
    return list(creds)


def revoke_credential(db: Session, credential: DbCredential) -> None:
    """Drop the role and mark the row inactive, even when the role is already gone."""
    try:
        revoke_db_credential(credential.pg_username)
    except Exception as e:
        logger.error(f"Failed to revoke Postgres role {credential.pg_username}: {e}")
        # Mark as inactive even if role drop fails (role may have been manually removed)
    credential.is_active = False
    db.commit()
