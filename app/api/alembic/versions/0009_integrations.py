"""Platform integration settings. No tenant_id: this row is for the whole platform.

RLS is forced and no policy is granted to vora_app, so a tenant session cannot
read the ciphertext. vora_admin bypasses RLS.

Revision ID: 0009_integrations
Revises: 0008_agents
Create Date: 2026-10-24

"""

import sqlalchemy as sa
from alembic import op

revision = "0009_integrations"
down_revision = "0008_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("secret_last4", sa.String(length=4), server_default="", nullable=False),
        sa.Column("value", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute("ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform_settings FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON platform_settings TO vora_admin")


def downgrade() -> None:
    op.drop_table("platform_settings")
