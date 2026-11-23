from datetime import date

from sqlalchemy import delete, select, update

from .BaseDataModel import BaseDataModel
from .db_schemes import StudyPlanRecord


class StudyPlanModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def _fetch(self, session, project_id: int):
        result = await session.execute(
            select(StudyPlanRecord).where(StudyPlanRecord.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_active_plan(self, project_id: int, today: date | None = None):
        """Return the saved plan. If its last exam day has passed, delete it and return None."""
        today = today or date.today()
        async with self.db_client() as session:
            record = await self._fetch(session, project_id)
            if record is not None and record.expires_on < today:
                await session.delete(record)
                await session.commit()
                return None
            return record

    async def save_project_plan(
        self,
        project_id: int,
        plan: dict,
        preferences: dict,
        note: str | None,
        expires_on: date,
    ):
        """Replace the project's plan with a new one in one transaction."""
        async with self.db_client() as session:
            async with session.begin():
                await session.execute(
                    delete(StudyPlanRecord).where(StudyPlanRecord.project_id == project_id)
                )
                session.add(
                    StudyPlanRecord(
                        project_id=project_id,
                        plan=plan,
                        preferences=preferences,
                        note=note,
                        expires_on=expires_on,
                    )
                )
            return await self._fetch(session, project_id)

    async def mark_stale(self, project_id: int) -> None:
        async with self.db_client() as session:
            async with session.begin():
                await session.execute(
                    update(StudyPlanRecord)
                    .where(StudyPlanRecord.project_id == project_id)
                    .values(is_stale=True)
                )

    async def delete_project_plan(self, project_id: int) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    delete(StudyPlanRecord).where(StudyPlanRecord.project_id == project_id)
                )
            return result.rowcount > 0
