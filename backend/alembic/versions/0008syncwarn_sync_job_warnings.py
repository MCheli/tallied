"""sync job warnings
Revision ID: 0008syncwarn
Revises: 0007ssearn
Create Date: 2026-10-30

A provider's warnings ("Connection to <bank> may need attention") were only logged, so a stale
bank looked current in the app. Each sync job keeps them so the app can show them.
Runs on an empty database.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008syncwarn"
down_revision: str | None = "0007ssearn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _schemas(conn) -> list[str]:
    return [r[0] for r in conn.execute(sa.text(
        "SELECT table_schema FROM information_schema.tables WHERE table_name = 'sync_jobs' AND table_schema LIKE 'tenant_%'"
    )).fetchall()]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _schemas(conn):
        conn.execute(sa.text(f'ALTER TABLE "{schema}".sync_jobs ADD COLUMN IF NOT EXISTS warnings JSON'))
    conn.execute(sa.text("SET search_path TO public"))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _schemas(conn):
        conn.execute(sa.text(f'ALTER TABLE "{schema}".sync_jobs DROP COLUMN IF EXISTS warnings'))
    conn.execute(sa.text("SET search_path TO public"))
