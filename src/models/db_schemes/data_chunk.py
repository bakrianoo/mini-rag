from pydantic import BaseModel,Field,field_validator
from typing import Optional
from bson.objectid import ObjectId

class DataChunk(BaseModel):
    id : Optional[ObjectId] = Field(None,alias='_id')
    chunk_text : str
    chunk_metadata: dict
    chunk_order: int = Field(...,gt=0)
    chunk_project_id : ObjectId
    chunk_asset_id : ObjectId
    @classmethod
    def get_indexes(cls):
        return [
            {
                "key" : {
                    "chunk_project_id" : 1
                },
                "name": 'chunk_project_id_index_1',
                'unique': False
            }
        ]

    class Config:
        arbitrary_types_allowed = True

class RetrievedDocument(BaseModel):
    text:str
    score:float

