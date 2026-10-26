from .BaseDataModel import BaseDataModel
from .db_schemes import Project
from sqlalchemy import func, select


class ProjectModel(BaseDataModel):
    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def create_project(self, project: Project | None = None):
        # Let PostgreSQL generate project_id.
        project = project or Project()

        async with self.db_client() as session:
            session.add(project)
            await session.commit()
            await session.refresh(project)

        return project

    async def get_project_by_id(self, project_id: int) -> Project | None:
        async with self.db_client() as session:
            result = await session.execute(
                select(Project).where(Project.project_id == project_id)
            )
            return result.scalar_one_or_none()

    async def get_all_projects(self, page: int = 1, page_size: int = 10):
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive.")

        async with self.db_client() as session:
            result = await session.execute(
                select(func.count(Project.project_id))
            )
            total_documents = result.scalar_one()
            total_pages = (total_documents + page_size - 1) // page_size

            result = await session.execute(
                select(Project)
                .order_by(Project.project_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            projects = result.scalars().all()

        return projects, total_pages
