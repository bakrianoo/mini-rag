import math
from .BaseDataModel import BaseDataModel
from .db_schemes import Project
from .enums.DataBaseEnum import DataBaseEnum

class ProjectModel(BaseDataModel):
    def __init__(self, db_client:object):
        super().__init__(db_client=db_client)
        self.collection = self.db_client[DataBaseEnum.COLLECTION_PROJECT_NAME.value]

    @classmethod
    async def create_instance(cls,db_client:object):
        instance = cls(db_client)
        await instance.init_collections()
        return instance
    
    async def init_collections(self):
        all_collections = await self.db_client.list_collection_names()
        if DataBaseEnum.COLLECTION_PROJECT_NAME.value not in all_collections:
            self.collection = self.db_client[DataBaseEnum.COLLECTION_PROJECT_NAME.value]
            indexes = Project.get_indexes()
            for index in indexes:
                await self.collection.create_index(
                    index['key'],
                    name=index['name'],
                    unique=index['unique']
                )

    async def create_project(self,project:Project):
        # converts the Pydantic model into a Python dictionary
        # exclude_unset It excludes fields that simply have default values but were never explicitly set.
        result = await self.collection.insert_one(project.model_dump(by_alias=True,exclude_unset=True))
        project.id = result.inserted_id
        return project

    async def get_or_create_project(self,project_id:str):
        record = await self.collection.find_one({
            'project_id':project_id
        })

        if record is None:
            project = Project(project_id=project_id)
            project = await self.create_project(project=project)
            return project
        return Project(**record)


    async def get_all_projects(self,page: int = 1,page_size: int = 10):
        if page < 1:
            raise ValueError("page must be greater than or equal to 1")

        if page_size < 1:
            raise ValueError("page_size must be greater than or equal to 1")

        total_documents = await self.collection.count_documents({})

        total_pages = math.ceil(total_documents / page_size)

        skip = (page - 1) * page_size

        cursor = await (
            self.collection
            .find({})
            .skip(skip)
            .limit(page_size)
        )

        projects = [
            Project(**document)
            for document in cursor
        ]

        return projects


