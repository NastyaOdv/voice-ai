"""create orchestrator tables

Revision ID: 0001
Revises:
Create Date: 2026-08-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "or_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_or_sessions_user_id", "or_sessions", ["user_id"])

    op.create_table(
        "or_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("audio_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["or_sessions.id"]),
    )
    op.create_index("ix_or_turns_session_id", "or_turns", ["session_id"])

    op.create_table(
        "or_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("you_said", sa.String(), nullable=False),
        sa.Column("better", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["turn_id"], ["or_turns.id"]),
    )
    op.create_index("ix_or_corrections_turn_id", "or_corrections", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_or_corrections_turn_id", table_name="or_corrections")
    op.drop_table("or_corrections")
    op.drop_index("ix_or_turns_session_id", table_name="or_turns")
    op.drop_table("or_turns")
    op.drop_index("ix_or_sessions_user_id", table_name="or_sessions")
    op.drop_table("or_sessions")
