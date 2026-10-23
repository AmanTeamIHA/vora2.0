"""Audit detail, tenant feature flags.

Revision ID: 0007_controls
Revises: 0006_numbers
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0007_controls"
down_revision = "0006_numbers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("detail", sa.Text(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("feature_flags", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tenants", "feature_flags")
    op.drop_column("audit_log", "detail")
