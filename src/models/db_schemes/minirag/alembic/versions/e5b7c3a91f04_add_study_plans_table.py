"""add study_plans table

Revision ID: e5b7c3a91f04
Revises: d41e8a7c5b92
Create Date: 2026-11-16 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e5b7c3a91f04"
down_revision: Union[str, None] = "d41e8a7c5b92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("plan_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "is_stale", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("expires_on", sa.Date(), nullable=False),
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
        sa.PrimaryKeyConstraint("plan_id"),
    )

    op.create_index(
        "ix_study_plans_project_id", "study_plans", ["project_id"], unique=True
    )
    op.create_index(
        "ix_study_plans_plan_uuid", "study_plans", ["plan_uuid"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_study_plans_plan_uuid", table_name="study_plans")
    op.drop_index("ix_study_plans_project_id", table_name="study_plans")
    op.drop_table("study_plans")
