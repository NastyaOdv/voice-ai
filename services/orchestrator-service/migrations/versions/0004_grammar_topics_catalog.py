"""create or_grammar_topics catalog, seed it, link or_user_mistakes.topic_id

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.data.grammar_topics import GRAMMAR_TOPICS

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "or_grammar_topics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_or_grammar_topics_name", "or_grammar_topics", ["name"])

    # Seed the catalog. Ids are assigned by the SERIAL sequence (not passed here).
    seed_table = sa.table(
        "or_grammar_topics",
        sa.column("level", sa.String),
        sa.column("category", sa.String),
        sa.column("name", sa.String),
    )
    op.bulk_insert(
        seed_table,
        [
            {"level": level, "category": category, "name": name}
            for level, category, name in GRAMMAR_TOPICS
        ],
    )

    op.add_column(
        "or_user_mistakes", sa.Column("topic_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_or_user_mistakes_topic_id",
        "or_user_mistakes",
        "or_grammar_topics",
        ["topic_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_or_user_mistakes_topic_id", "or_user_mistakes", type_="foreignkey"
    )
    op.drop_column("or_user_mistakes", "topic_id")
    op.drop_index("ix_or_grammar_topics_name", table_name="or_grammar_topics")
    op.drop_table("or_grammar_topics")
