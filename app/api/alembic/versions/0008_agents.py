"""Agents, immutable versions, and the call's agent_version.

Revision ID: 0008_agents
Revises: 0007_controls
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0008_agents"
down_revision = "0007_controls"
branch_labels = None
depends_on = None

_CONFIG = (
    "CREATE OR REPLACE FUNCTION reject_agent_version_config_update() RETURNS trigger AS $$ "
    "BEGIN "
    "IF NEW.config::text IS DISTINCT FROM OLD.config::text THEN "
    "RAISE EXCEPTION 'agent version config is immutable'; "
    "END IF; "
    "RETURN NEW; "
    "END $$ LANGUAGE plpgsql"
)


def _rls(table: str) -> None:
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


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("deployed_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('draft', 'committed', 'deployed')",
            name="agent_versions_state",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(
        "agents_deployed_version_fk",
        "agents",
        "agent_versions",
        ["deployed_version_id"],
        ["id"],
    )
    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(_CONFIG)
    op.execute(
        """
        CREATE TRIGGER agent_versions_config_immutable
        BEFORE UPDATE ON agent_versions
        FOR EACH ROW EXECUTE FUNCTION reject_agent_version_config_update()
        """
    )
    for table in ("agents", "agent_versions", "calls"):
        _rls(table)


def downgrade() -> None:
    for table in ("calls", "agent_versions", "agents"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute("DROP TRIGGER IF EXISTS agent_versions_config_immutable ON agent_versions")
    op.execute("DROP FUNCTION IF EXISTS reject_agent_version_config_update()")
    op.drop_table("calls")
    op.drop_constraint("agents_deployed_version_fk", "agents", type_="foreignkey")
    op.drop_table("agent_versions")
    op.drop_table("agents")
