from ..VectorDBInterface import VectorDBInterface
from ..VectorDBEnum import DistanceMethodEnums
from qdrant_client import models,QdrantClient
import logging
from typing import List
from models.db_schemes import RetrievedDocument
class QdrantDBProvider(VectorDBInterface):
    def __init__(self,db_path: str, distance_method: str):
        self.client = None
        self.db_path = db_path
        self.distance_method = distance_method

        if distance_method == DistanceMethodEnums.COSINE.value:
            self.distance_method = DistanceMethodEnums.COSINE.value
        elif distance_method == DistanceMethodEnums.DOT.value:
            self.distance_method = DistanceMethodEnums.DOT.value

        self.logger = logging.getLogger(__name__)

    def connect(self):
        self.client = QdrantClient(path=self.db_path)
    def disconnect(self):
        self.client = None
    def is_collection_exists(self, colllection_name) -> bool:
        return self.client.collection_exists(collection_name=colllection_name)
    def list_all_collection(self) -> List:
        return self.client.get_collections()
    def get_collection_info(self,collection_name:str) -> dict:
        return self.client.get_collection(collection_name=collection_name)
    def delete_collection(self,collection_name:str):
        if self.is_collection_exists(colllection_name=collection_name):
            self.client.delete_collection(collection_name=collection_name)
    def create_collection(self,collection_name:str,
                              embedding_size:int,
                              do_reset:bool = False):
        if do_reset:
            _ = self.delete_collection(collection_name=collection_name)
        if not self.is_collection_exists(colllection_name=collection_name):
            _ = self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_size,
                    distance=self.distance_method
                )
            )
            return True
        return False

    
    def insert_one(self,collection_name:str,
                       text:str,vector:list,
                       metadata:dict = None,
                       record_id:str = None):
        if not self.is_collection_exists(colllection_name=collection_name):
            self.logger.error('not existed collection')
            return False
        try:
            _ = self.client.upsert(
                collection_name=collection_name,
                points=[
                    models.PointStruct(
                        id = [record_id],
                        vector=vector,
                        payload={ # if any error raise here add id parameter
                            'text':text,
                            'metadata':metadata
                        }
                    )
                ]
            )
            return True
        except Exception as e:
            self.logger.error('error while inserting')
            return False

    def insert_many(self,collection_name:str,
                       texts:str,vectors:list,
                       metadatas:list = None,
                       record_ids:str = None,
                       batch_size:int=50):
        if not self.is_collection_exists(colllection_name=collection_name):
            self.logger.error('not existed collection')
            return False
        if not metadatas:
            metadatas = [None] * len(texts)
        if not record_ids:
            record_ids = list(range(0,len(texts)))
        if not (len(texts) == len(metadatas) == len(record_ids) == len(vectors)):
            self.logger.error('Input lists must have the same length')
            return False
        for i in range(0,len(texts),batch_size):
            batch_end = i + batch_size
            batch_texts = texts[i:batch_end]
            batch_vectors = vectors[i:batch_end]
            batch_metadatas = metadatas[i:batch_end]
            batch_record_ids = record_ids[i:batch_end]
            batch_points = [
                models.PointStruct(
                    id=batch_record_ids[j]
                    ,vector=batch_vectors[j],
                    payload={
                        'text':batch_texts[j],
                        'metadata':batch_metadatas[j]
                    }
                )
                for j in range(len(batch_texts))
            ]

            try:
                _ = self.client.upsert(
                    collection_name=collection_name,
                    points=batch_points
                )
                
            except Exception as e:
                self.logger.error('error while inserting')
                return False

        return True



    def search_by_vector(
        self,
        collection_name: str,
        vector: List[float],
        limit: int = 5
        ):

        if not self.is_collection_exists(collection_name):
            self.logger.error(
                f"Collection '{collection_name}' does not exist"
            )
            return None

        if not vector:
            self.logger.error("Vector cannot be empty")
            return None

        if limit <= 0:
            self.logger.error("Limit must be greater than zero")
            return None

        results =  self.client.query_points(
            collection_name=collection_name,
            query=vector,
            limit=limit
        )

        return [
            RetrievedDocument(**{
                'score':result.score,
                'text':result.payload['text']
            })
            for result in results.points
        ]


        
