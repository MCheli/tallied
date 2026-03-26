"""add email receipt tables

Revision ID: a1b2c3d4e5f6
Revises: 877cad9a2d80
Create Date: 2026-03-25 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '877cad9a2d80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create email tables: email_forwarding_addresses (public) + email_receipts (per-tenant)."""
    conn = op.get_bind()

    # Platform table in public schema
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS public.email_forwarding_addresses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            email VARCHAR NOT NULL UNIQUE,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT now()
        )
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_email_fwd_email
        ON public.email_forwarding_addresses (email)
    """))

    # Tenant-scoped table in each tenant schema
    result = conn.execute(sa.text("SELECT schema_name FROM tenants"))
    schemas = [row[0] for row in result]

    for schema in schemas:
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".email_receipts (
                id SERIAL PRIMARY KEY,
                from_email VARCHAR NOT NULL,
                forwarded_by VARCHAR NOT NULL,
                subject VARCHAR NOT NULL,
                body_text TEXT,
                body_html TEXT,
                status VARCHAR,
                parsed_data TEXT,
                error_message TEXT,
                transaction_id VARCHAR,
                created_at TIMESTAMP DEFAULT now()
            )
        """))


def downgrade() -> None:
    """Drop email tables."""
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT schema_name FROM tenants"))
    schemas = [row[0] for row in result]

    for schema in schemas:
        op.drop_table('email_receipts', schema=schema)

    op.drop_table('email_forwarding_addresses')
