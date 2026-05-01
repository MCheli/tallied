"""add monarch_sync_jobs table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-01 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_tenant_schemas() -> list[str]:
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
            CREATE TABLE IF NOT EXISTS monarch_sync_jobs (
                id SERIAL PRIMARY KEY,
                status VARCHAR NOT NULL,
                trigger VARCHAR NOT NULL DEFAULT 'manual',
                started_at TIMESTAMP NOT NULL DEFAULT now(),
                finished_at TIMESTAMP,
                balances_synced INTEGER DEFAULT 0,
                txn_added INTEGER DEFAULT 0,
                txn_updated INTEGER DEFAULT 0,
                error TEXT
            )
        """))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_monarch_sync_jobs_status_started "
            "ON monarch_sync_jobs (status, started_at)"
        ))
    conn.execute(sa.text('SET search_path TO public'))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _get_tenant_schemas():
        conn.execute(sa.text(f'SET search_path TO "{schema}"'))
        conn.execute(sa.text("DROP TABLE IF EXISTS monarch_sync_jobs"))
    conn.execute(sa.text('SET search_path TO public'))
