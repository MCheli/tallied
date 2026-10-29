"""platform tables in public

Revision ID: 0001platform
Revises:
Create Date: 2026-10-29

The root of the chain. Creates the platform tables in `public` (users, tenants,
tenant_memberships, api_keys, api_usage_logs, db_credentials,
webhook_subscriptions, audit_logs, email_forwarding_addresses) so that
`alembic upgrade head` on an empty database produces a bootable system.

Before this revision the platform tables were only ever created by
Base.metadata.create_all() in the app's startup, which is exactly what this
revision does (checkfirst, so databases that already have them are untouched).
Tenant tables are still created per tenant by create_tenant_schema(); later
revisions that touch them iterate the tenant schemas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001platform"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.database import Base
    from app.services.tenant_service import platform_tables
    import app.models  # noqa: F401 — register every model on Base.metadata

    conn = op.get_bind()
    conn.execute(sa.text("SET search_path TO public"))
    Base.metadata.create_all(bind=conn, tables=platform_tables(), checkfirst=True)


def downgrade() -> None:
    # Dropping the platform tables destroys every user and tenant; refuse.
    raise RuntimeError("0001platform cannot be downgraded")
