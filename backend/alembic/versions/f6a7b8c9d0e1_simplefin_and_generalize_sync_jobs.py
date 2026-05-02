"""Add SimpleFIN tables; rename monarch_sync_jobs → sync_jobs with provider

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-02 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
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

        # ── 1. Generalize monarch_sync_jobs → sync_jobs ────────────────────
        # Add provider column (defaults existing rows to 'monarch'), drop the
        # old single-running index, rename the table, then create the new
        # per-provider index. Idempotent in case migrations re-run.
        has_old = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'monarch_sync_jobs'"
        )).first()
        has_new = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'sync_jobs'"
        )).first()

        if has_old and not has_new:
            conn.execute(sa.text(
                "ALTER TABLE monarch_sync_jobs "
                "ADD COLUMN IF NOT EXISTS provider VARCHAR NOT NULL DEFAULT 'monarch'"
            ))
            conn.execute(sa.text("DROP INDEX IF EXISTS uq_monarch_sync_jobs_one_running"))
            conn.execute(sa.text("ALTER TABLE monarch_sync_jobs RENAME TO sync_jobs"))
        elif not has_new:
            # Fresh tenant — create directly. (Older tenants had monarch_sync_jobs
            # via Base.metadata.create_all in seed/dev paths.)
            conn.execute(sa.text("""
                CREATE TABLE sync_jobs (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR NOT NULL,
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
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_jobs_one_running_per_provider "
            "ON sync_jobs (provider) WHERE status = 'running'"
        ))

        # ── 2. SimpleFIN tables ────────────────────────────────────────────
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS simplefin_links (
                id SERIAL PRIMARY KEY,
                access_url TEXT NOT NULL,
                last_synced_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """))
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS simplefin_account_configs (
                id SERIAL PRIMARY KEY,
                simplefin_link_id INTEGER NOT NULL
                    REFERENCES simplefin_links(id) ON DELETE CASCADE,
                simplefin_account_id VARCHAR NOT NULL,
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
        conn.execute(sa.text("DROP TABLE IF EXISTS simplefin_account_configs"))
        conn.execute(sa.text("DROP TABLE IF EXISTS simplefin_links"))
        conn.execute(sa.text("DROP INDEX IF EXISTS uq_sync_jobs_one_running_per_provider"))
        conn.execute(sa.text("ALTER TABLE IF EXISTS sync_jobs RENAME TO monarch_sync_jobs"))
        conn.execute(sa.text("ALTER TABLE IF EXISTS monarch_sync_jobs DROP COLUMN IF EXISTS provider"))
        conn.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_monarch_sync_jobs_one_running "
            "ON monarch_sync_jobs (status) WHERE status = 'running'"
        ))
    conn.execute(sa.text('SET search_path TO public'))
