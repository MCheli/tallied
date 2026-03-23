"""Service for managing Postgres roles for tenant direct access."""
import secrets
import logging

from sqlalchemy import text

from app.database import engine
from app.config import settings

logger = logging.getLogger("tallied")


def _parse_db_host_port() -> tuple[str, int, str]:
    """Extract host, port, database from the database URL."""
    from urllib.parse import urlparse
    parsed = urlparse(settings.database_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    database = (parsed.path or "/tallied").lstrip("/")
    return host, port, database


def create_db_credential(tenant_schema: str, access_level: str = "read") -> dict:
    """Create a Postgres role with access to the tenant schema.

    Returns: {username, password, host, port, database, schema, connection_string}
    """
    username = f"tld_{tenant_schema[:20]}_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    host, port, database = _parse_db_host_port()

    with engine.connect() as conn:
        # Create role with login
        conn.execute(text(f'CREATE ROLE "{username}" LOGIN PASSWORD :pw'), {"pw": password})

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
