"""Disabled users and invite tokens for platform and tenant members.

Revision ID: 0005_users
Revises: 0004_plans
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0005_users"
down_revision = "0004_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_table(
        "user_invites",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role_name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("ALTER TABLE user_invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_invites FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON user_invites
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON user_invites TO vora_app, vora_admin")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON user_invites")
    op.drop_table("user_invites")
    op.drop_column("users", "disabled")
