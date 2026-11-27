import hashlib
import json
import uuid
from datetime import timedelta
from sqlalchemy import select, delete, update, func, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from models.db_schemes.minirag.schemes.celery_task_execution import CeleryTaskExecution


class TaskInProgress(Exception):
    """Another worker owns this task right now: retry later, don't run."""


class IdempotencyManager:

    def __init__(self, db_client, db_engine):
        self.db_client = db_client
        self.db_engine = db_engine

    def create_args_hash(self, task_name: str, task_args: dict):
        combined_data = {
            **task_args,
            "task_name": task_name
        }
        json_string = json.dumps(combined_data, sort_keys=True, default=str)
        return hashlib.sha256(json_string.encode()).hexdigest()

    async def claim_task(self, task_name: str, task_args: dict,
                         celery_task_id: str, lease_seconds: int = 660):
        """
        Atomic claim in ONE statement (no SELECT then INSERT race).
        Identity = (task_name, celery_task_id): a retry keeps the same id.

        Returns (execution_id, existing_record):
          (id, None)       -> we own the task, run it.
          (None, record)   -> somebody else owns it / it already succeeded.
        Time comes from the DB (now()), so no timezone mismatch.
        """
        task_uuid = uuid.UUID(str(celery_task_id))
        args_hash = self.create_args_hash(task_name, task_args)

        stmt = pg_insert(CeleryTaskExecution).values(
            task_name=task_name,
            task_args_hash=args_hash,
            task_args=task_args,
            celery_task_id=task_uuid,
            status='STARTED',
            started_at=func.now(),
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=[CeleryTaskExecution.task_name,
                            CeleryTaskExecution.celery_task_id],
            set_={
                "status": "STARTED",
                "started_at": func.now(),
                "completed_at": None,
                "result": None,
                "updated_at": func.now(),
            },
            where=or_(
                # previous attempt failed: we can take it right away
                CeleryTaskExecution.status.in_(['FAILURE', 'RETRY']),
                # previous attempt looks dead (worker crashed): lease expired
                and_(
                    CeleryTaskExecution.status.in_(['PENDING', 'STARTED']),
                    CeleryTaskExecution.started_at
                    < func.now() - timedelta(seconds=lease_seconds),
                ),
            ),
        ).returning(CeleryTaskExecution.execution_id)

        session = self.db_client()
        try:
            result = await session.execute(stmt)
            execution_id = result.scalar_one_or_none()
            await session.commit()

            if execution_id is not None:
                return execution_id, None

            existing = await session.execute(
                select(CeleryTaskExecution).where(
                    CeleryTaskExecution.task_name == task_name,
                    CeleryTaskExecution.celery_task_id == task_uuid,
                )
            )
            return None, existing.scalar_one_or_none()
        finally:
            await session.close()

    async def update_task_status(self, execution_id: int, status: str, result: dict = None):
        """Update task status and result."""
        values = {"status": status, "updated_at": func.now()}
        if result is not None:
            values["result"] = result
        if status in ['SUCCESS', 'FAILURE']:
            values["completed_at"] = func.now()

        session = self.db_client()
        try:
            await session.execute(
                update(CeleryTaskExecution)
                .where(CeleryTaskExecution.execution_id == execution_id)
                .values(**values)
            )
            await session.commit()
        finally:
            await session.close()

    async def cleanup_old_tasks(self, time_retention: int = 86400,
                                stuck_retention: int = 604800) -> int:
        """
        Delete finished task records older than time_retention seconds.
        PENDING/STARTED records are only deleted after stuck_retention
        (default 7 days), so a running task never loses its record.
        Returns:
            Number of deleted records
        """
        finished_cutoff = func.now() - timedelta(seconds=time_retention)
        stuck_cutoff = func.now() - timedelta(seconds=stuck_retention)

        session = self.db_client()
        try:
            stmt = delete(CeleryTaskExecution).where(
                or_(
                    and_(
                        CeleryTaskExecution.status.in_(['SUCCESS', 'FAILURE']),
                        CeleryTaskExecution.created_at < finished_cutoff,
                    ),
                    CeleryTaskExecution.created_at < stuck_cutoff,
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        finally:
            await session.close()
