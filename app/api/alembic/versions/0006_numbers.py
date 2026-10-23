"""Phone numbers and caller-ID pools.

Revision ID: 0006_numbers
Revises: 0005_users
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0006_numbers"
down_revision = "0005_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "caller_id_pools",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="caller_id_pools_tenant_name"),
    )
    op.create_table(
        "phone_numbers",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("pool_id", sa.Uuid(), nullable=True),
        sa.Column("e164", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="free", nullable=False),
        sa.Column("inbound_agent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('free', 'assigned', 'blocked')",
            name="phone_numbers_status",
        ),
        sa.CheckConstraint(
            "status <> 'free' OR (tenant_id IS NULL AND pool_id IS NULL AND inbound_agent_id IS NULL)",
            name="phone_numbers_free_unassigned",
        ),
        sa.CheckConstraint(
            "status <> 'assigned' OR tenant_id IS NOT NULL",
            name="phone_numbers_assigned_tenant",
        ),
        sa.ForeignKeyConstraint(["pool_id"], ["caller_id_pools.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("e164"),
    )
    op.create_index("phone_numbers_tenant_idx", "phone_numbers", ["tenant_id"])
    for table in ("caller_id_pools", "phone_numbers"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO vora_app, vora_admin")


def downgrade() -> None:
    for table in ("phone_numbers", "caller_id_pools"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index("phone_numbers_tenant_idx", table_name="phone_numbers")
    op.drop_table("phone_numbers")
    op.drop_table("caller_id_pools")
