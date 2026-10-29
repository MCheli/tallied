"""vehicle valuation labels

Revision ID: 0003vehval
Revises: 0002removal
Create Date: 2026-10-29

AI vehicle values are stored as labelled estimates (AI-3 / DEC-3): the source,
the model id and the model's confidence sit next to the number.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003vehval"
down_revision: Union[str, None] = "0002removal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ("valuation_source", "valuation_model", "valuation_confidence")


def upgrade() -> None:
    conn = op.get_bind()
    schemas = [r[0] for r in conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
    )).fetchall()]
    for schema in schemas:
        for col in COLUMNS:
            conn.execute(sa.text(f'ALTER TABLE "{schema}".vehicles ADD COLUMN IF NOT EXISTS {col} VARCHAR'))
    conn.execute(sa.text("SET search_path TO public"))


def downgrade() -> None:
    conn = op.get_bind()
    schemas = [r[0] for r in conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
    )).fetchall()]
    for schema in schemas:
        for col in COLUMNS:
            conn.execute(sa.text(f'ALTER TABLE "{schema}".vehicles DROP COLUMN IF EXISTS {col}'))
    conn.execute(sa.text("SET search_path TO public"))
