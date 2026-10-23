"""Tenant profile, status, plan, and the first admin invite.

Revision ID: 0003_tenants
Revises: 0002_auth
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0003_tenants"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("slug", sa.String(length=80), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("legal_name", sa.String(length=200), server_default="", nullable=False),
    )
    op.add_column("tenants", sa.Column("gstin", sa.String(length=15), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("contact_name", sa.String(length=200), server_default="", nullable=False),
    )
    op.add_column(
        "tenants",
        sa.Column("contact_email", sa.String(length=320), server_default="", nullable=False),
    )
    op.add_column("tenants", sa.Column("contact_phone", sa.String(length=32), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
    )
    op.add_column("tenants", sa.Column("plan_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("tenants_slug_key", "tenants", ["slug"])
    op.create_foreign_key("tenants_plan_id_fkey", "tenants", "plans", ["plan_id"], ["id"])
    op.create_index("tenants_status_idx", "tenants", ["status"])

    op.create_table(
        "tenant_invites",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role_name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "email", name="tenant_invites_tenant_email_key"),
    )
    op.execute("ALTER TABLE tenant_invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_invites FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON tenant_invites
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_invites TO vora_app, vora_admin")
    op.execute(
        "INSERT INTO plans (name) SELECT 'Starter' "
        "WHERE NOT EXISTS (SELECT 1 FROM plans WHERE name = 'Starter')"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_invites")
    op.drop_table("tenant_invites")
    op.drop_index("tenants_status_idx", table_name="tenants")
    op.drop_constraint("tenants_plan_id_fkey", "tenants", type_="foreignkey")
    op.execute("DELETE FROM plans WHERE name = 'Starter'")
    op.drop_constraint("tenants_slug_key", "tenants", type_="unique")
    for column in (
        "plan_id",
        "status",
        "contact_phone",
        "contact_email",
        "contact_name",
        "gstin",
        "legal_name",
        "slug",
    ):
        op.drop_column("tenants", column)
