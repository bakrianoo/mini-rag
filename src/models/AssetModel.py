from .BaseDataModel import BaseDataModel
from .db_schemes import Asset
from .enums.DataBaseEnum import DataBaseEnum
from bson.objectid import ObjectId

class AssetModel(BaseDataModel):
    def __init__(self, db_client:object):
        super().__init__(db_client=db_client)
        self.collection = self.db_client[DataBaseEnum.COLLECTION_ASSET_NAME.value]

    @classmethod
    async def create_instance(cls,db_client:object):
        instance = cls(db_client)
        await instance.init_collections()
        return instance
    
    async def init_collections(self):
        all_collections = await self.db_client.list_collection_names()
        if DataBaseEnum.COLLECTION_ASSET_NAME.value not in all_collections:
            self.collection = self.db_client[DataBaseEnum.COLLECTION_ASSET_NAME.value]
            indexes = Asset.get_indexes()
            for index in indexes:
                await self.collection.create_index(
                    index['key'],
                    name=index['name'],
                    unique=index['unique']
                )

    
    async def create_asset(self,asset:Asset):
        result = await self.collection.insert_one(asset.model_dump(by_alias=True,exclude={"id"}))
        asset.id = result.inserted_id
        return asset

    async def get_all_project_assets(self,asset_project_id:str,asset_type:str):
        records =  await self.collection.find({
            'asset_project_id':ObjectId(asset_project_id),
            'asset_type':asset_type
        }).to_list(length=None)


        return [
            Asset(**record)
            for record in records
        ]


    async def get_asset_record(self,asset_project_id:str,asset_name:str):
        record = await self.collection.find_one({
            'asset_project_id':asset_project_id,
            'asset_name':asset_name
        })

        if record:
            return Asset(**record)

        return None