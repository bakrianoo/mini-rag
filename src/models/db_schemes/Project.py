from pydantic import BaseModel,Field,field_validator
from typing import Optional
from bson.objectid import ObjectId

class Project(BaseModel):
    id : Optional[ObjectId] = Field(None,alias='_id')
    # MongoDB uses _id as the document's unique identifier, similar to a primary key in SQL.
    project_id: str = Field(...,min_length=1)

    @field_validator('project_id')
    @classmethod
    def validate_project_id(cls,value:str):
        if not value.isalnum():
            raise ValueError('project_id must be alpha numeric')
        return value

    @classmethod
    def get_indexes(cls):
        return [
            {
                # key can be dictionary or list of tuple 
                "key": {
                    "project_id": 1 # 1 -> ascending , -1 -> descending
                },
                "name": "project_id_index_1",
                "unique": True
            } # you can add more dictionaries
        ]

    class Config:
        arbitrary_types_allowed = True
        