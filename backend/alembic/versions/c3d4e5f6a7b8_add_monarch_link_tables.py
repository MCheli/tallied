"""add monarch_links and monarch_account_configs tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-04 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_tenant_schemas() -> list[str]:
    """Return all tenant schema names."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'")
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _get_tenant_schemas():
        conn.execute(sa.text(f'SET search_path TO "{schema}"'))
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS monarch_links (
                id SERIAL PRIMARY KEY,
                email VARCHAR NOT NULL,
                token TEXT NOT NULL,
                last_synced_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """))
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS monarch_account_configs (
                id SERIAL PRIMARY KEY,
                monarch_link_id INTEGER NOT NULL REFERENCES monarch_links(id) ON DELETE CASCADE,
                monarch_account_id VARCHAR NOT NULL,
                account_name VARCHAR NOT NULL,
                account_type VARCHAR,
                institution VARCHAR,
                sync_balances BOOLEAN DEFAULT TRUE,
                sync_transactions BOOLEAN DEFAULT FALSE,
                local_account_id VARCHAR,
                created_at TIMESTAMP DEFAULT now()
            )
        """))
    conn.execute(sa.text('SET search_path TO public'))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _get_tenant_schemas():
        conn.execute(sa.text(f'SET search_path TO "{schema}"'))
        conn.execute(sa.text("DROP TABLE IF EXISTS monarch_account_configs"))
        conn.execute(sa.text("DROP TABLE IF EXISTS monarch_links"))
    conn.execute(sa.text('SET search_path TO public'))
