"""add card_id to assets and quizzes

Revision ID: 7c1d2e3f4a5b
Revises: 4b48d5365a89
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7c1d2e3f4a5b"
down_revision: Union[str, None] = "4b48d5365a89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS card_id INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assets_card_id ON assets (card_id)")

    op.execute("ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS card_id INTEGER NOT NULL DEFAULT 0")
    op.execute("CREATE INDEX IF NOT EXISTS ix_quizzes_card_id ON quizzes (card_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_quizzes_card_id")
    op.execute("ALTER TABLE quizzes DROP COLUMN IF EXISTS card_id")

    op.execute("DROP INDEX IF EXISTS ix_assets_card_id")
    op.execute("ALTER TABLE assets DROP COLUMN IF EXISTS card_id")
