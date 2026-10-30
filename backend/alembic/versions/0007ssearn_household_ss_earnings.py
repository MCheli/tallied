"""household Social Security earnings record

Revision ID: 0007ssearn
Revises: 0006planv2
Create Date: 2026-10-30

The Social Security statement's estimate assumes work at the taxable maximum until claiming.
Storing the earnings record lets the plan reduce the benefit for years not worked when retiring
early. Runs on an empty database.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007ssearn"
down_revision: str | None = "0006planv2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _schemas(conn) -> list[str]:
    return [r[0] for r in conn.execute(sa.text(
        "SELECT table_schema FROM information_schema.tables WHERE table_name = 'household_profile' AND table_schema LIKE 'tenant_%'"
    )).fetchall()]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _schemas(conn):
        conn.execute(sa.text(f'ALTER TABLE "{schema}".household_profile ADD COLUMN IF NOT EXISTS ss_earnings JSON'))
    conn.execute(sa.text("SET search_path TO public"))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _schemas(conn):
        conn.execute(sa.text(f'ALTER TABLE "{schema}".household_profile DROP COLUMN IF EXISTS ss_earnings'))
    conn.execute(sa.text("SET search_path TO public"))
