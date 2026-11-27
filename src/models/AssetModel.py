from .BaseDataModel import BaseDataModel
from .db_schemes import Asset
from sqlalchemy.future import select


class AssetModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client)
        return instance

    async def create_asset(self, asset: Asset):
        async with self.db_client() as session:
            async with session.begin():
                session.add(asset)
            await session.commit()
            await session.refresh(asset)
        return asset

    async def get_all_project_assets(self, asset_project_id: int, asset_type: str, card_id: int | None = None):
        async with self.db_client() as session:
            conditions  = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_type == asset_type,
            )
            if card_id is not None:
              conditions = conditions.where(
                 Asset.card_id == card_id
                    )

            result =  await session.execute(conditions)
            return result.scalars().all()

    async def get_asset_record(self, asset_project_id: int, asset_name: str , card_id: int | None = None):
        async with self.db_client() as session:
            stmt = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_name == asset_name,            
            )
            if card_id is not None:
                stmt = stmt.where(Asset.card_id == card_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
        return record
    
    async def get_asset_by_id(self, project_id: int, asset_id: int):
        async with self.db_client() as session:
            result = await session.execute(
               select(Asset).where(
                Asset.asset_id == asset_id,
                Asset.asset_project_id == project_id,
            )
          )
        return result.scalar_one_or_none()
