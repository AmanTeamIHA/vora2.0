"""Plan limits and per-tenant overrides for concurrency and rates.

Revision ID: 0004_plans
Revises: 0003_tenants
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0004_plans"
down_revision = "0003_tenants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("per_minute_rate_paise", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "plans",
        sa.Column("transfer_leg_rate_paise", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "plans",
        sa.Column("max_concurrent_calls", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "plans",
        sa.Column("max_outbound_share_percent", sa.Integer(), server_default="100", nullable=False),
    )
    op.add_column(
        "plans",
        sa.Column("max_agents", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "plans",
        sa.Column("languages", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.add_column(
        "plans",
        sa.Column("feature_flags", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
    )
    op.create_table(
        "tenant_limits",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("max_concurrent_calls", sa.Integer(), nullable=True),
        sa.Column("per_minute_rate_paise", sa.Integer(), nullable=True),
        sa.Column("transfer_leg_rate_paise", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.execute("ALTER TABLE tenant_limits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_limits FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON tenant_limits
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_limits TO vora_app, vora_admin")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_limits")
    op.drop_table("tenant_limits")
    for column in (
        "feature_flags",
        "languages",
        "max_agents",
        "max_outbound_share_percent",
        "max_concurrent_calls",
        "transfer_leg_rate_paise",
        "per_minute_rate_paise",
    ):
        op.drop_column("plans", column)
