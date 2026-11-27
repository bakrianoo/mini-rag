import logging
from sqlalchemy import delete, select, text as sql_text

from .BaseDataModel import BaseDataModel
from .db_schemes import Asset, DataChunk
from stores.vectordb.VectorDBEnums import PgVectorTableSchemeEnums

logger = logging.getLogger(__name__)


class CardModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def delete_card_data(self, project_id: int, card_id: int, collection_name: str) -> dict:
        """
        Deletes everything that belongs to a card in ONE transaction.
        Returns counts plus the asset file names (so the caller can remove
        the files from disk after the commit).
        """
        async with self.db_client() as session:
            async with session.begin():

                rows = (await session.execute(
                    select(Asset.asset_id, Asset.asset_name).where(
                        Asset.asset_project_id == project_id,
                        Asset.card_id == card_id,
                    )
                )).all()
                asset_ids = [r[0] for r in rows]
                asset_names = [r[1] for r in rows]

                # 1) vectors (the collection may not exist if nothing was ever indexed)
                vectors_deleted = 0
                table_exists = (await session.execute(
                    sql_text("SELECT to_regclass(:name)::text"),
                    {"name": collection_name},
                )).scalar()
                if table_exists:
                    result = await session.execute(
                        sql_text(
                            f"DELETE FROM {collection_name} "
                            f"WHERE {PgVectorTableSchemeEnums.METADATA.value}->>'card_id' = :card_id"
                        ),
                        {"card_id": str(card_id)},
                    )
                    vectors_deleted = result.rowcount or 0

                # 2) chunks of the card's files
                chunks_deleted = 0
                if asset_ids:
                    result = await session.execute(
                        delete(DataChunk).where(DataChunk.chunk_asset_id.in_(asset_ids))
                    )
                    chunks_deleted = result.rowcount or 0

                # 3) chat messages, then images (messages reference images)
                result = await session.execute(
                    sql_text("DELETE FROM vision_messages WHERE project_id = :p AND card_id = :c"),
                    {"p": project_id, "c": card_id},
                )
                messages_deleted = result.rowcount or 0

                result = await session.execute(
                    sql_text("DELETE FROM vision_images WHERE project_id = :p AND card_id = :c"),
                    {"p": project_id, "c": card_id},
                )
                images_deleted = result.rowcount or 0

                # 4) asset records (after their chunks)
                assets_deleted = 0
                if asset_ids:
                    result = await session.execute(
                        delete(Asset).where(Asset.asset_id.in_(asset_ids))
                    )
                    assets_deleted = result.rowcount or 0

        logger.warning(
            "card deleted | project_id=%s card_id=%s vectors=%s chunks=%s "
            "messages=%s images=%s assets=%s",
            project_id, card_id, vectors_deleted, chunks_deleted,
            messages_deleted, images_deleted, assets_deleted,
        )

        return {
            "vectors": vectors_deleted,
            "chunks": chunks_deleted,
            "messages": messages_deleted,
            "images": images_deleted,
            "assets": assets_deleted,
            "asset_names": asset_names,
        }