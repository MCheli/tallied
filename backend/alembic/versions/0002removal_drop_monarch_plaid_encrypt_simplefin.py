"""drop monarch and plaid tables; encrypt simplefin access urls

Revision ID: 0002removal
Revises: f6a7b8c9d0e1
Create Date: 2026-10-29

Monarch and Plaid were removed (docs/research/monarch-postmortem.md, DEC-1,
DEC-2). Their per-tenant tables go. SimpleFIN access URLs are now stored
encrypted (SEC-3); existing plaintext rows are encrypted in place.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002removal"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_schemas(conn) -> list[str]:
    return [r[0] for r in conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
    )).fetchall()]


def upgrade() -> None:
    from app.services.crypto import encrypt_secret, is_encrypted

    conn = op.get_bind()
    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".monarch_account_configs'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".monarch_links'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".plaid_links'))

        has_links = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = :s AND table_name = 'simplefin_links'"
        ), {"s": schema}).scalar()
        if not has_links:
            continue
        rows = conn.execute(sa.text(f'SELECT id, access_url FROM "{schema}".simplefin_links')).fetchall()
        for row_id, access_url in rows:
            if access_url and not is_encrypted(access_url):
                conn.execute(
                    sa.text(f'UPDATE "{schema}".simplefin_links SET access_url = :v WHERE id = :id'),
                    {"v": encrypt_secret(access_url), "id": row_id},
                )
    conn.execute(sa.text("SET search_path TO public"))


def downgrade() -> None:
    # Credentials stay encrypted; the dropped tables are not recreated.
    pass
