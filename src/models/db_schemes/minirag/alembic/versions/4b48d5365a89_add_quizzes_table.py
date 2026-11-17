
"""add quizzes table

Revision ID: 4b48d5365a89
Revises: 243ca8b683b0
Create Date: 2026-10-17 16:13:06.871207
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "4b48d5365a89"
down_revision: Union[str, None] = "243ca8b683b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column(
            "quiz_id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "quiz_uuid",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "questions",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("quiz_id"),
        sa.UniqueConstraint("quiz_uuid"),
    )

    op.create_index(
        "ix_quizzes_project_id",
        "quizzes",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_quizzes_quiz_uuid",
        "quizzes",
        ["quiz_uuid"],
        unique=True,
    )
    op.create_index(
        "ix_quizzes_status",
        "quizzes",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quizzes_status", table_name="quizzes")
    op.drop_index("ix_quizzes_quiz_uuid", table_name="quizzes")
    op.drop_index("ix_quizzes_project_id", table_name="quizzes")
    op.drop_table("quizzes")
