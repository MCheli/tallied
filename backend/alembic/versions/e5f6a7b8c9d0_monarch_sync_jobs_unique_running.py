"""unique partial index on monarch_sync_jobs(status='running')

Prevents two concurrent POST /api/v1/monarch/sync calls from inserting two
'running' rows for the same tenant. The route handler catches the resulting
IntegrityError and returns the existing in-flight job_id.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-01 23:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
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
        # First, collapse any pre-existing duplicate 'running' rows so the
        # unique index can be created. Keep the most recent, fail the rest.
        conn.execute(sa.text("""
            UPDATE monarch_sync_jobs
               SET status='failed',
                   error='superseded by newer running job',
                   finished_at=now()
             WHERE status='running'
               AND id NOT IN (
                   SELECT MAX(id) FROM monarch_sync_jobs WHERE status='running'
               )
        """))
        conn.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_monarch_sync_jobs_one_running "
            "ON monarch_sync_jobs (status) WHERE status = 'running'"
        ))
    conn.execute(sa.text('SET search_path TO public'))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _get_tenant_schemas():
        conn.execute(sa.text(f'SET search_path TO "{schema}"'))
        conn.execute(sa.text("DROP INDEX IF EXISTS uq_monarch_sync_jobs_one_running"))
    conn.execute(sa.text('SET search_path TO public'))
