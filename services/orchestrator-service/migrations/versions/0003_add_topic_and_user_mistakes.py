"""add topic to or_corrections and create or_user_mistakes

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "or_corrections",
        sa.Column("topic", sa.String(), server_default="", nullable=False),
    )

    op.create_table(
        "or_user_mistakes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("example", sa.String(), nullable=False),
        sa.Column("better", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["or_sessions.id"]),
        sa.ForeignKeyConstraint(["turn_id"], ["or_turns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_or_user_mistakes_user_id", "or_user_mistakes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_or_user_mistakes_user_id", table_name="or_user_mistakes")
    op.drop_table("or_user_mistakes")
    op.drop_column("or_corrections", "topic")
