"""celery_task_executions: unique by (task_name, celery_task_id)

Revision ID: a3f1c9d7e582
Revises: e5b7c3a91f04
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3f1c9d7e582"
down_revision: Union[str, None] = "e5b7c3a91f04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # the old args-based unique indexes block legitimate re-processing
    op.execute("DROP INDEX IF EXISTS ixz_task_name_args_hash")
    op.execute("DROP INDEX IF EXISTS ixz_task_name_args_celery_hash")

    # keep the newest row per (task_name, celery_task_id) so the new unique index can be built
    op.execute("""
        DELETE FROM celery_task_executions a
        USING celery_task_executions b
        WHERE a.celery_task_id IS NOT NULL
          AND a.task_name = b.task_name
          AND a.celery_task_id = b.celery_task_id
          AND a.execution_id < b.execution_id
    """)

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ixz_task_name_celery_task_id "
        "ON celery_task_executions (task_name, celery_task_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ixz_task_name_celery_task_id")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ixz_task_name_args_celery_hash "
        "ON celery_task_executions (task_name, task_args_hash, celery_task_id)"
    )
