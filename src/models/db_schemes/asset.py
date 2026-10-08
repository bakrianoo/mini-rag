from pydantic import BaseModel,Field,field_validator
from typing import Optional
from bson.objectid import ObjectId
from datetime import datetime,timezone

class Asset(BaseModel):
    id : Optional[ObjectId] = Field(None,alias='_id')
    # MongoDB uses _id as the document's unique identifier, similar to a primary key in SQL.
    asset_project_id: ObjectId
    asset_type: str = Field(...,min_length=1)
    asset_name: str = Field(...,min_length=1)
    asset_size: int = Field(ge=0,default=None)
    asset_config: Optional[dict] = Field(None)
    asset_pushed_at : datetime = Field(default_factory=lambda:datetime.now(timezone.utc)) 
    
    # don't use default parameter in datetime.now(timezone.utc) , because every intance will have same time
    

    @classmethod
    def get_indexes(cls):
        return [
            {
                # key can be dictionary or list of tuple 
                "key": {
                    "asset_project_id": 1 # 1 -> ascending , -1 -> descending
                },
                "name": "asset_project_id_index_1",
                "unique": False
            } ,
            {
                # key can be dictionary or list of tuple 
                "key": {
                    "asset_project_id": 1,
                    'asset_name':1
                },
                "name": "asset_project_id_name_index_1",
                "unique": True
            }
        ]

    class Config:
        arbitrary_types_allowed = True
        