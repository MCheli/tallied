"""backfill property and 401(k) balances into net worth

Revision ID: 0004nwbackfill
Revises: 0003vehval
Create Date: 2026-10-30

Decision D2 makes property valuations and 401(k) statements write balance
snapshots, but data saved before that change never did: net worth counted the
mortgage and not the house, and a tenant without an investment_401k account
never counted the 401(k). This writes the missing snapshots (and the 401(k)
account) once per tenant using app.services.balances.backfill_asset_balances,
which is idempotent. Runs on an empty database (no tenant schemas: no-op).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from alembic import op

revision: str = "0004nwbackfill"
down_revision: str | None = "0003vehval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.services.balances import backfill_asset_balances

    conn = op.get_bind()
    schemas = [r[0] for r in conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
    )).fetchall()]
    for schema in schemas:
        tables = {r[0] for r in conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = :s"
        ), {"s": schema}).fetchall()}
        if not {"accounts", "balance_snapshots", "property_valuations", "retirement_accounts"} <= tables:
            continue
        conn.execute(sa.text(f'SET search_path TO "{schema}", public'))
        session = Session(bind=conn)
        counts = backfill_asset_balances(session)
        session.flush()
        session.close()
        print(f"0004nwbackfill {schema}: {counts}")
    conn.execute(sa.text("SET search_path TO public"))


def downgrade() -> None:
    # Snapshots are data, not schema; leaving them is harmless and removing them
    # would take the house and 401(k) back out of net worth.
    pass
