"""add email receipt tables

Revision ID: a1b2c3d4e5f6
Revises: 877cad9a2d80
Create Date: 2026-03-25 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '877cad9a2d80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create email_receipts table in all existing tenant schemas."""
    # Get all tenant schemas
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT schema_name FROM tenants"))
    schemas = [row[0] for row in result]

    for schema in schemas:
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".email_receipts (
                id SERIAL PRIMARY KEY,
                from_email VARCHAR NOT NULL,
                forwarded_by VARCHAR NOT NULL,
                subject VARCHAR NOT NULL,
                body_text TEXT,
                body_html TEXT,
                status VARCHAR,
                parsed_data TEXT,
                error_message TEXT,
                transaction_id VARCHAR,
                created_at TIMESTAMP DEFAULT now()
            )
        """))


def downgrade() -> None:
    """Drop email_receipts from all tenant schemas."""
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT schema_name FROM tenants"))
    schemas = [row[0] for row in result]

    for schema in schemas:
        op.drop_table('email_receipts', schema=schema)
