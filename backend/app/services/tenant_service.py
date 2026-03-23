"""Tenant schema management — create and manage per-tenant PostgreSQL schemas."""
from sqlalchemy import text

from app.database import Base, engine

# Tables that live in the public schema (not per-tenant)
PLATFORM_TABLES = {"users", "tenants", "tenant_memberships", "api_keys", "api_usage_logs", "db_credentials", "webhook_subscriptions", "audit_logs", "alembic_version"}


def create_tenant_schema(schema_name: str):
    """Create a new PostgreSQL schema and populate it with all financial tables."""
    tenant_tables = [t for t in Base.metadata.sorted_tables if t.name not in PLATFORM_TABLES]

    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        conn.execute(text(f'SET search_path TO "{schema_name}"'))
        Base.metadata.create_all(bind=conn, tables=tenant_tables)
        conn.commit()


def drop_tenant_schema(schema_name: str):
    """Drop a tenant's schema and all its data. Use with caution."""
    with engine.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        conn.commit()
