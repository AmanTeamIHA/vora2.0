"""Call lifecycle columns, turns, and recordings.

Revision ID: 0009_call_lifecycle
Revises: 0008_agents
Create Date: 2026-10-24

"""

import sqlalchemy as sa
from alembic import op

revision = "0009_call_lifecycle"
down_revision = "0008_agents"
branch_labels = None
depends_on = None


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
    op.add_column(
        "calls",
        sa.Column("status", sa.String(length=16), server_default="created", nullable=False),
    )
    op.add_column("calls", sa.Column("ringing_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("end_reason", sa.Text(), nullable=True))
    op.add_column("calls", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "calls_status",
        "calls",
        "status IN ('created', 'ringing', 'answered', 'ended')",
    )
    op.create_check_constraint(
        "calls_duration_ms_nonneg",
        "calls",
        "duration_ms IS NULL OR duration_ms >= 0",
    )
    op.create_index("calls_tenant_id_idx", "calls", ["tenant_id"])

    op.create_table(
        "call_turns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("stt_ms", sa.Integer(), nullable=False),
        sa.Column("llm_ms", sa.Integer(), nullable=False),
        sa.Column("tts_ms", sa.Integer(), nullable=False),
        sa.Column("ttfw_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("turn_index >= 0", name="call_turns_index_nonneg"),
        sa.CheckConstraint(
            "stt_ms >= 0 AND llm_ms >= 0 AND tts_ms >= 0 AND ttfw_ms >= 0",
            name="call_turns_latency_nonneg",
        ),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_id", "turn_index", name="call_turns_call_index"),
    )
    op.create_index("call_turns_tenant_id_idx", "call_turns", ["tenant_id"])
    op.create_index("call_turns_call_id_idx", "call_turns", ["call_id"])

    op.create_table(
        "call_recordings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("recording_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_key", name="call_recordings_key"),
    )
    op.create_index("call_recordings_tenant_id_idx", "call_recordings", ["tenant_id"])
    op.create_index("call_recordings_call_id_idx", "call_recordings", ["call_id"])

    for table in ("call_turns", "call_recordings"):
        _rls(table)


def downgrade() -> None:
    op.drop_table("call_recordings")
    op.drop_table("call_turns")
    op.drop_index("calls_tenant_id_idx", table_name="calls")
    op.drop_constraint("calls_duration_ms_nonneg", "calls", type_="check")
    op.drop_constraint("calls_status", "calls", type_="check")
    op.drop_column("calls", "duration_ms")
    op.drop_column("calls", "end_reason")
    op.drop_column("calls", "ended_at")
    op.drop_column("calls", "answered_at")
    op.drop_column("calls", "ringing_at")
    op.drop_column("calls", "status")
