from sqlalchemy import delete, select

from .BaseDataModel import BaseDataModel
from .db_schemes import ExamEntry


class ExamEntryModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def _fetch(self, session, project_id: int):
        result = await session.execute(
            select(ExamEntry)
            .where(ExamEntry.project_id == project_id)
            .order_by(ExamEntry.exam_date, ExamEntry.exam_time, ExamEntry.exam_id)
        )
        return result.scalars().all()

    async def get_project_exams(self, project_id: int):
        async with self.db_client() as session:
            return await self._fetch(session, project_id)
    
    async def delete_project_exams(self, project_id: int) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    delete(ExamEntry).where(ExamEntry.project_id == project_id)
                )
            return result.rowcount > 0
    async def replace_project_exams(self, project_id: int, exams: list[dict]):
        """Delete the project's old schedule and save the new one in one transaction."""
        async with self.db_client() as session:
            async with session.begin():
                await session.execute(
                    delete(ExamEntry).where(ExamEntry.project_id == project_id)
                )
                session.add_all(
                    [
                        ExamEntry(
                            project_id=project_id,
                            subject=exam["subject"],
                            exam_date=exam["exam_date"],
                            exam_time=exam.get("exam_time"),
                        )
                        for exam in exams
                    ]
                )
            return await self._fetch(session, project_id)
    
    
