from ..VectorDBInterface import VectorDBInterface
from ..VectorDBEnums import (DistanceMethodEnums, PgVectorTableSchemeEnums, 
                             PgVectorDistanceMethodEnums, PgVectorIndexTypeEnums)
import logging
from typing import List
from models.db_schemes import RetrievedDocument
from sqlalchemy.sql import text as sql_text ,bindparam
import json



class InsertVerificationError(Exception):
    pass

class PGVectorProvider(VectorDBInterface):

    def __init__(self, db_client, default_vector_size: int = 786,
                       distance_method: str = None, index_threshold: int=100):
        
        self.db_client = db_client
        self.default_vector_size = default_vector_size
        
        self.index_threshold = index_threshold

        self.logger = logging.getLogger("uvicorn")

        # search_by_vector always ranks with the cosine operator (<=>), so the
        # index must use cosine too, otherwise the index doesn't match the query.
        if distance_method != DistanceMethodEnums.COSINE.value:
            self.logger.warning(
                f"PGVector search uses cosine, ignoring distance_method={distance_method!r}"
            )
        distance_method = PgVectorDistanceMethodEnums.COSINE.value

        self.pgvector_table_prefix = PgVectorTableSchemeEnums._PREFIX.value
        self.distance_method = distance_method
        self.default_index_name = lambda collection_name: f"{collection_name}_vector_idx"


    async def connect(self):
        async with self.db_client() as session:
            try:
                # Check if vector extension already exists
                result = await session.execute(sql_text(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                ))
                extension_exists = result.scalar_one_or_none()
                
                if not extension_exists:
                    # Only create if it doesn't exist
                    await session.execute(sql_text("CREATE EXTENSION vector"))
                    await session.commit()
            except Exception as e:
                # If extension already exists or any other error, just log and continue
                self.logger.warning(f"Vector extension setup: {str(e)}")
                await session.rollback()

    async def disconnect(self):
        pass

    async def is_collection_existed(self, collection_name: str) -> bool:

        record = None
        async with self.db_client() as session:
            async with session.begin():
                list_tbl = sql_text(f'SELECT * FROM pg_tables WHERE tablename = :collection_name')
                results = await session.execute(list_tbl, {"collection_name": collection_name})
                record = results.scalar_one_or_none()

        return record
    
    async def list_all_collections(self) -> List:
        records = []
        async with self.db_client() as session:
            async with session.begin():
                list_tbl = sql_text('SELECT tablename FROM pg_tables WHERE tablename LIKE :prefix')
                results = await session.execute(list_tbl, {"prefix": self.pgvector_table_prefix})
                records = results.scalars().all()
        
        return records
    
    async def get_collection_info(self, collection_name: str) -> dict:
        async with self.db_client() as session:
            async with session.begin():
                
                table_info_sql = sql_text(f'''
                    SELECT schemaname, tablename, tableowner, tablespace, hasindexes 
                    FROM pg_tables 
                    WHERE tablename = :collection_name
                ''')

                count_sql = sql_text(f'SELECT COUNT(*) FROM {collection_name}')

                table_info = await session.execute(table_info_sql, {"collection_name": collection_name})
                record_count = await session.execute(count_sql)

                table_data = table_info.fetchone()
                if not table_data:
                    return None
                
                return {
                    "table_info": {
                        "schemaname": table_data[0],
                        "tablename": table_data[1],
                        "tableowner": table_data[2],
                        "tablespace": table_data[3],
                        "hasindexes": table_data[4],
                    },
                    "record_count": record_count.scalar_one(),
                }
            
    async def delete_collection(self, collection_name: str):
        async with self.db_client() as session:
            async with session.begin():
                self.logger.info(f"Deleting collection: {collection_name}")

                delete_sql = sql_text(f'DROP TABLE IF EXISTS {collection_name}')
                await session.execute(delete_sql)
                await session.commit()
        
        return True

    async def create_collection(self, collection_name: str,
                                      embedding_size: int,
                                      do_reset: bool = False):
        
        if do_reset:
            _ = await self.delete_collection(collection_name=collection_name)

        is_collection_existed = await self.is_collection_existed(collection_name=collection_name)
        if not is_collection_existed:
            self.logger.info(f"Creating collection: {collection_name}")
            async with self.db_client() as session:
                async with session.begin():
                    create_sql = sql_text(
    f'CREATE TABLE {collection_name} ('
        f'{PgVectorTableSchemeEnums.ID.value} bigserial PRIMARY KEY,'
        f'{PgVectorTableSchemeEnums.TEXT.value} text, '
        f'{PgVectorTableSchemeEnums.VECTOR.value} vector({embedding_size}), '
        f'{PgVectorTableSchemeEnums.METADATA.value} jsonb DEFAULT \'{{}}\', '
        f'{PgVectorTableSchemeEnums.CHUNK_ID.value} integer UNIQUE, '  
        f'FOREIGN KEY ({PgVectorTableSchemeEnums.CHUNK_ID.value}) REFERENCES chunks(chunk_id)'
    ')'
)
                    await session.execute(create_sql)
                    await session.commit()
            
            return True

        return False
    
    async def is_index_existed(self, collection_name: str) -> bool:
        index_name = self.default_index_name(collection_name)
        async with self.db_client() as session:
            async with session.begin():
                check_sql = sql_text(f""" 
                                    SELECT 1 
                                    FROM pg_indexes 
                                    WHERE tablename = :collection_name
                                    AND indexname = :index_name
                                    """)
                results = await session.execute(check_sql, {"index_name": index_name, "collection_name": collection_name})
                
                return bool(results.scalar_one_or_none())
            
    async def create_vector_index(self, collection_name: str,
                                        index_type: str = PgVectorIndexTypeEnums.HNSW.value):
        is_index_existed = await self.is_index_existed(collection_name=collection_name)
        if is_index_existed:
            return False
        
        async with self.db_client() as session:
            async with session.begin():
                count_sql = sql_text(f'SELECT COUNT(*) FROM {collection_name}')
                result = await session.execute(count_sql)
                records_count = result.scalar_one()

                if records_count < self.index_threshold:
                    return False
                
                self.logger.info(f"START: Creating vector index for collection: {collection_name}")
                
                index_name = self.default_index_name(collection_name)
                create_idx_sql = sql_text(
                                            f'CREATE INDEX {index_name} ON {collection_name} '
                                            f'USING {index_type} ({PgVectorTableSchemeEnums.VECTOR.value} {self.distance_method})'
                                          )

                await session.execute(create_idx_sql)

                self.logger.info(f"END: Created vector index for collection: {collection_name}")

    async def reset_vector_index(self, collection_name: str, 
                                       index_type: str = PgVectorIndexTypeEnums.HNSW.value) -> bool:
        
        index_name = self.default_index_name(collection_name)
        async with self.db_client() as session:
            async with session.begin():
                drop_sql = sql_text(f'DROP INDEX IF EXISTS {index_name}')
                await session.execute(drop_sql)
        
        return await self.create_vector_index(collection_name=collection_name, index_type=index_type)

    
    async def insert_one(self, collection_name: str, text: str, vector: list,
                            metadata: dict = None,
                            record_id: str = None):
        
        is_collection_existed = await self.is_collection_existed(collection_name=collection_name)
        if not is_collection_existed:
            self.logger.error(f"Can not insert new record to non-existed collection: {collection_name}")
            return False
        
        if not record_id:
            self.logger.error(f"Can not insert new record without chunk_id: {collection_name}")
            return False
        
        async with self.db_client() as session:
            async with session.begin():
                insert_sql = sql_text(f'INSERT INTO {collection_name} '
                                      f'({PgVectorTableSchemeEnums.TEXT.value}, {PgVectorTableSchemeEnums.VECTOR.value}, {PgVectorTableSchemeEnums.METADATA.value}, {PgVectorTableSchemeEnums.CHUNK_ID.value}) '
                                      'VALUES (:text, :vector, :metadata, :chunk_id)'
                                      )
                
                metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else "{}"
                await session.execute(insert_sql, {
                    'text': text,
                    'vector': "[" + ",".join([ str(v) for v in vector ]) + "]",
                    'metadata': metadata_json,
                    'chunk_id': record_id
                })
                await session.commit()

                await self.create_vector_index(collection_name=collection_name)
        
        return True
    

    async def insert_many(self, collection_name: str, texts: list,
                          vectors: list, metadata: list = None,
                          record_ids: list = None, batch_size: int = 50):

        is_collection_existed = await self.is_collection_existed(collection_name=collection_name)
        if not is_collection_existed:
            self.logger.error(f"Can not insert new records to non-existed collection: {collection_name}")
            return False

        if record_ids is None or not (len(texts) == len(vectors) == len(record_ids)):
            self.logger.error(f"Invalid data items for collection: {collection_name}")
            return False

        if not metadata:
            metadata = [None] * len(texts)
        elif len(metadata) != len(texts):
            self.logger.error(f"Metadata length mismatch for collection: {collection_name}")
            return False

        try:
            async with self.db_client() as session:
                async with session.begin():
                    for i in range(0, len(texts), batch_size):
                        batch_texts = texts[i:i+batch_size]
                        batch_vectors = vectors[i:i + batch_size]
                        batch_metadata = metadata[i:i + batch_size]
                        batch_record_ids = record_ids[i:i + batch_size]

                        values = []

                        for _text, _vector, _metadata, _record_id in zip(batch_texts, batch_vectors, batch_metadata, batch_record_ids):
                            metadata_json = json.dumps(_metadata, ensure_ascii=False) if _metadata is not None else "{}"
                            values.append({
                                'text': _text,
                                'vector': "[" + ",".join([str(v) for v in _vector]) + "]",
                                'metadata': metadata_json,
                                'chunk_id': _record_id
                            })

                        batch_insert_sql = sql_text(f'INSERT INTO {collection_name} '
                                        f'({PgVectorTableSchemeEnums.TEXT.value}, '
                                        f'{PgVectorTableSchemeEnums.VECTOR.value}, '
                                        f'{PgVectorTableSchemeEnums.METADATA.value}, '
                                        f'{PgVectorTableSchemeEnums.CHUNK_ID.value}) '
                                        f'VALUES (:text, :vector, :metadata, :chunk_id)'
                                        f'ON CONFLICT ({PgVectorTableSchemeEnums.CHUNK_ID.value}) DO NOTHING')

                        await session.execute(batch_insert_sql, values)

                    # still inside the transaction: if this raises, everything rolls back
                    await self._verify_inserted(
                        session, collection_name, record_ids, metadata
                    )
        except InsertVerificationError as e:
            self.logger.error(f"Insert verification failed for {collection_name}: {e}")
            return False

        await self.create_vector_index(collection_name=collection_name)

        return True

        
    async def delete_records_by_chunk_ids(self, collection_name: str,
                                          chunk_ids: list, step: int = 1000) -> int:
        if not chunk_ids:
            return 0

        if not await self.is_collection_existed(collection_name=collection_name):
            return 0

        delete_sql = sql_text(
            f'DELETE FROM {collection_name} '
            f'WHERE {PgVectorTableSchemeEnums.CHUNK_ID.value} IN :ids'
        ).bindparams(bindparam("ids", expanding=True))

        deleted = 0
        async with self.db_client() as session:
            async with session.begin():
                for i in range(0, len(chunk_ids), step):
                    result = await session.execute(
                        delete_sql, {"ids": chunk_ids[i:i + step]}
                    )
                    deleted += result.rowcount or 0

        return deleted


    async def _verify_inserted(self, session, collection_name: str,
                               record_ids: list, metadata: list, step: int = 1000):
        expected = {
            rid: (json.loads(json.dumps(meta)) if meta is not None else {})
            for rid, meta in zip(record_ids, metadata)
        }

        select_sql = sql_text(
            f'SELECT {PgVectorTableSchemeEnums.CHUNK_ID.value}, '
            f'{PgVectorTableSchemeEnums.METADATA.value} '
            f'FROM {collection_name} '
            f'WHERE {PgVectorTableSchemeEnums.CHUNK_ID.value} IN :ids'
        ).bindparams(bindparam("ids", expanding=True))

        found = {}
        ids = list(expected.keys())
        for i in range(0, len(ids), step):
            result = await session.execute(select_sql, {"ids": ids[i:i + step]})
            for row in result.fetchall():
                stored = row[1]
                if isinstance(stored, str):
                    stored = json.loads(stored)
                found[row[0]] = stored or {}

        missing = [rid for rid in expected if rid not in found]
        mismatched = [rid for rid in expected if rid in found and found[rid] != expected[rid]]

        if missing or mismatched:
            raise InsertVerificationError(
                f"expected={len(expected)} missing={len(missing)} "
                f"metadata_mismatch={len(mismatched)} "
                f"sample={(missing + mismatched)[:5]}"
            )
    async def search_by_vector(self, collection_name: str, vector: list, limit: int, card_id: int ):
     is_collection_existed = await self.is_collection_existed(
        collection_name=collection_name
    )

     if not is_collection_existed:
        self.logger.error(
            f"Can not search for records in a non-existed collection: {collection_name}"
        )
        return False

     vector = "[" + ",".join(str(v) for v in vector) + "]"

     async with self.db_client() as session:
        async with session.begin():
            search_sql = sql_text(
                f"""
                SELECT text,metadata, score
                FROM (
                    SELECT
                        {PgVectorTableSchemeEnums.TEXT.value} AS text,
                        {PgVectorTableSchemeEnums.METADATA.value} AS metadata,

                        1 - (
                            {PgVectorTableSchemeEnums.VECTOR.value}
                            <=> :vector
                        ) AS score,
                        ROW_NUMBER() OVER (
                            PARTITION BY {PgVectorTableSchemeEnums.TEXT.value}
                            ORDER BY (
                                {PgVectorTableSchemeEnums.VECTOR.value}
                                <=> :vector
                            ) ASC
                        ) AS rn
                    FROM {collection_name}
                    WHERE {PgVectorTableSchemeEnums.METADATA.value}
                        ->> 'card_id' = :card_id
                ) AS ranked
                WHERE rn = 1
                ORDER BY score DESC
                LIMIT :limit
                """
            )

            result = await session.execute(
                search_sql,
                {
                    "vector": vector,
                    "limit": limit,
                    "card_id": str(card_id),

                },
            )

            records = result.fetchall()

            return [
                RetrievedDocument(
                    text=record.text,
                    score=record.score,
                    metadata=record.metadata or {},

                )
                for record in records
            ]
