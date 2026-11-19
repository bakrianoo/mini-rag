"""add exam_entries table

Revision ID: d41e8a7c5b92
Revises: 7c1d2e3f4a5b
Create Date: 2026-11-16 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d41e8a7c5b92"
down_revision: Union[str, None] = "7c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exam_entries",
        sa.Column("exam_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exam_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column("exam_time", sa.Time(), nullable=True),
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
        sa.PrimaryKeyConstraint("exam_id"),
    )

    op.create_index(
        "ix_exam_entries_project_id", "exam_entries", ["project_id"], unique=False
    )
    op.create_index(
        "ix_exam_entries_exam_uuid", "exam_entries", ["exam_uuid"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_exam_entries_exam_uuid", table_name="exam_entries")
    op.drop_index("ix_exam_entries_project_id", table_name="exam_entries")
    op.drop_table("exam_entries")
