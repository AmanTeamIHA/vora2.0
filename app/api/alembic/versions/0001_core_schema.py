"""Core tables and row-level security.

Revision ID: 0001_core_schema
Revises:
Create Date: 2026-10-23

"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0001_core_schema"
down_revision = None
branch_labels = None
depends_on = None

# Local compose and CI only. Production role passwords come from Secrets Manager.
_LOCAL_ROLE_PASSWORD = "vora"


def _role_exists(name: str) -> bool:
    return (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": name})
        .scalar()
        is not None
    )


def _create_login_role(name: str, bypass: bool) -> None:
    if _role_exists(name):
        return
    env_name = "VORA_ADMIN_PASSWORD" if name == "vora_admin" else "VORA_APP_PASSWORD"
    password = os.environ.get(env_name, _LOCAL_ROLE_PASSWORD).replace("'", "''")
    bypass_sql = "BYPASSRLS" if bypass else "NOBYPASSRLS"
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE ROLE {name} LOGIN PASSWORD '{password}' NOSUPERUSER {bypass_sql} NOINHERIT"
        )


def _enable_rls(table: str, column: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        USING ({column}::text = current_setting('app.tenant_id', true))
        WITH CHECK ({column}::text = current_setting('app.tenant_id', true))
        """
    )


def upgrade() -> None:
    _create_login_role("vora_app", bypass=False)
    _create_login_role("vora_admin", bypass=True)

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("parent_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.execute(
        """
        CREATE FUNCTION tenants_set_tenant_id() RETURNS trigger AS $$
        BEGIN
          NEW.tenant_id := NEW.id;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER tenants_set_tenant_id
        BEFORE INSERT OR UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION tenants_set_tenant_id()
        """
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX user_roles_tenant_unique
        ON user_roles (user_id, role_id, tenant_id)
        WHERE tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX user_roles_platform_unique
        ON user_roles (user_id, role_id)
        WHERE tenant_id IS NULL
        """
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("users_tenant_id_idx", "users", ["tenant_id"])
    op.create_index("user_roles_tenant_id_idx", "user_roles", ["tenant_id"])
    op.create_index("audit_log_tenant_id_idx", "audit_log", ["tenant_id"])

    for table, column in (
        ("tenants", "tenant_id"),
        ("users", "tenant_id"),
        ("user_roles", "tenant_id"),
        ("audit_log", "tenant_id"),
    ):
        _enable_rls(table, column)

    database = op.get_bind().engine.url.database
    op.execute(f'GRANT CONNECT ON DATABASE "{database}" TO vora_app, vora_admin')
    op.execute("GRANT USAGE ON SCHEMA public TO vora_app, vora_admin")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, users, user_roles TO vora_app")
    op.execute("GRANT SELECT ON roles, plans TO vora_app")
    op.execute("GRANT SELECT, INSERT ON audit_log TO vora_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, users, roles, user_roles, plans TO vora_admin"
    )
    op.execute("GRANT SELECT, INSERT ON audit_log TO vora_admin")

    roles = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("scope", sa.String),
    )
    op.bulk_insert(
        roles,
        [
            {"name": "Owner", "scope": "platform"},
            {"name": "Platform Admin", "scope": "platform"},
            {"name": "Support", "scope": "platform"},
            {"name": "Finance", "scope": "platform"},
            {"name": "Read-only", "scope": "platform"},
            {"name": "Tenant Admin", "scope": "tenant"},
            {"name": "Manager", "scope": "tenant"},
            {"name": "Agent Builder", "scope": "tenant"},
            {"name": "Human Agent", "scope": "tenant"},
            {"name": "Viewer", "scope": "tenant"},
        ],
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log, user_roles, plans, users, roles, tenants CASCADE")
    op.execute("DROP FUNCTION IF EXISTS tenants_set_tenant_id() CASCADE")
    with op.get_context().autocommit_block():
        op.execute("DROP ROLE IF EXISTS vora_app")
        op.execute("DROP ROLE IF EXISTS vora_admin")
