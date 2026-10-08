from bson.objectid import ObjectId
from .BaseDataModel import BaseDataModel
from .db_schemes.data_chunk import DataChunk
from .enums.DataBaseEnum import DataBaseEnum
from pymongo import InsertOne
import math
class ChunkModel(BaseDataModel):
    def __init__(self, db_client):
        super().__init__(db_client)
        self.collection = self.db_client[DataBaseEnum.COLLECTION_CHUNK_NAME.value]


    @classmethod
    async def create_instance(cls,db_client:object):
        instance = cls(db_client)
        await instance.init_collections()
        return instance
    
    async def init_collections(self):
        all_collections = await self.db_client.list_collection_names()
        if DataBaseEnum.COLLECTION_CHUNK_NAME.value not in all_collections:
            self.collection = self.db_client[DataBaseEnum.COLLECTION_CHUNK_NAME.value]
            indexes = DataChunk.get_indexes()
            for index in indexes:
                await self.collection.create_index(
                    index['key'],
                    name=index['name'],
                    unique=index['unique']
                )
    
    async def insert_chunk(self,chunk: DataChunk):
        result = await self.collection.insert_one(chunk.model_dump(by_alias=True,exclude_unset=True))
        chunk.id = result.inserted_id
        return chunk

    async def get_chunk(self,chunk_id:str):
        result = await self.collection.fine_one({'_id':ObjectId(chunk_id)})
        if result is None:
            return None
        return DataChunk(**result)

    async def insert_many_chunks(self,chunks:list,batch_size=100):

        for i in range(0,len(chunks),batch_size):
            batch = chunks[i:i+batch_size]

            operations = [
                InsertOne(chunk.model_dump(by_alias=True,exclude_unset=True))
                for chunk in batch
            ]

            await self.collection.bulk_write(operations)

        return len(chunks)

    async def delete_chunks_by_project_id(self,project_id:str):
        result = await self.collection.delete_many({
            "chunk_project_id" : project_id
        })

        return result.deleted_count

    async def get_project_chunks(self,project_id:ObjectId,
                                 page:int = 1 , page_size:int = 100):
        if page < 1 :
            raise ValueError("page must be greater than or equal to 1")
        if page_size < 1:
            raise ValueError("page_size must be greater than or equal to 1")
        records = await self.collection.find({
            'chunk_project_id':project_id
        }).skip((page-1)*page_size).limit(page_size).to_list(length=None)

        return [
            DataChunk(**record)
            for record in records
        ]
