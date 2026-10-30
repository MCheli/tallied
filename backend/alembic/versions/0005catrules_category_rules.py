"""category rules and category source

Revision ID: 0005catrules
Revises: 0004nwbackfill
Create Date: 2026-10-30

The sync provider sends no categories. Each tenant gets a category_rules table
(merchant -> category, applied on every sync) and transactions.category_source,
which says who set a category (a rule, an email receipt, or the owner by hand)
so rules never overwrite the owner's choice. Also indexes transactions.account_id,
which every spending query filters on (CODE-7). Runs on an empty database.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005catrules"
down_revision: str | None = "0004nwbackfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _schemas(conn) -> list[str]:
    return [r[0] for r in conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
    )).fetchall()]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _schemas(conn):
        has_txn = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = :s AND table_name = 'transactions'"
        ), {"s": schema}).first()
        if not has_txn:
            continue
        conn.execute(sa.text(f'''
            CREATE TABLE IF NOT EXISTS "{schema}".category_rules (
                id SERIAL PRIMARY KEY,
                pattern VARCHAR NOT NULL,
                match VARCHAR NOT NULL DEFAULT 'contains',
                account_type VARCHAR,
                direction VARCHAR,
                category VARCHAR NOT NULL,
                category_group VARCHAR NOT NULL,
                source VARCHAR NOT NULL DEFAULT 'manual',
                note TEXT,
                priority INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT now()
            )'''))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".transactions ADD COLUMN IF NOT EXISTS category_source VARCHAR'))
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS ix_transactions_account_id ON "{schema}".transactions (account_id)'))
    conn.execute(sa.text("SET search_path TO public"))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _schemas(conn):
        conn.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}".ix_transactions_account_id'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".transactions DROP COLUMN IF EXISTS category_source'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".category_rules'))
    conn.execute(sa.text("SET search_path TO public"))
