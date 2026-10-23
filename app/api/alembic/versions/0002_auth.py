"""Password and TOTP columns on users.

Revision ID: 0002_auth
Revises: 0001_core_schema
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0002_auth"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "totp_confirmed")
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "password_hash")
