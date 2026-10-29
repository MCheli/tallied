"""Tenant schema management — create tenant schemas and open sessions bound to them.

`tenant_session(schema)` is the one way to get a Session that stays on a tenant
schema across commits. A bare `SET search_path` is undone by the pool-checkout
listener in app.database as soon as the connection is recycled (which happens
after every commit), so every tenant-scoped code path (request dependency, email
webhook, scheduler, seed) must go through this helper.
"""
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine

# Tables that live in the public schema (not per-tenant)
PLATFORM_TABLES = {
    "users",
    "tenants",
    "tenant_memberships",
    "api_keys",
    "api_usage_logs",
    "db_credentials",
    "webhook_subscriptions",
    "audit_logs",
    "alembic_version",
    "email_forwarding_addresses",
}


def platform_tables():
    """SQLAlchemy Table objects for the public schema, in dependency order."""
    import app.models  # noqa: F401 — make sure every model is registered on Base.metadata

    return [t for t in Base.metadata.sorted_tables if t.name in PLATFORM_TABLES]


def tenant_tables():
    """SQLAlchemy Table objects that live in each tenant schema, in dependency order."""
    import app.models  # noqa: F401

    return [t for t in Base.metadata.sorted_tables if t.name not in PLATFORM_TABLES]


def create_tenant_schema(schema_name: str):
    """Create a new PostgreSQL schema and populate it with all financial tables."""
    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        conn.execute(text(f'SET search_path TO "{schema_name}"'))
        Base.metadata.create_all(bind=conn, tables=tenant_tables())
        conn.commit()


def drop_tenant_schema(schema_name: str):
    """Drop a tenant's schema and all its data. Use with caution."""
    with engine.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        conn.commit()


def validate_schema_name(schema: str) -> bool:
    from app.models.tenant import Tenant

    return Tenant.validate_schema_name(schema)


@contextmanager
def tenant_session(schema: str, *, include_public: bool = True) -> Generator[Session, None, None]:
    """Yield a Session whose search_path is the tenant schema on every transaction.

    `include_public=True` appends `public` so ORM queries that join platform
    tables from a tenant session keep working; pass False for anything that must
    not resolve platform tables (the SQL runner does its own SET LOCAL instead).

    The session is rolled back and closed on exit; callers commit explicitly.
    """
    if not validate_schema_name(schema):
        raise ValueError(f"Invalid tenant schema name: {schema!r}")

    path = f'"{schema}", public' if include_public else f'"{schema}"'

    def _set_search_path(session, transaction, connection):
        connection.execute(text(f"SET search_path TO {path}"))

    db = SessionLocal()
    event.listen(db, "after_begin", _set_search_path)
    try:
        # Force a connection + transaction so search_path is set immediately
        db.connection().execute(text(f"SET search_path TO {path}"))
        yield db
    finally:
        event.remove(db, "after_begin", _set_search_path)
        try:
            db.rollback()
        except Exception:  # pragma: no cover - connection already gone
            pass
        db.close()
