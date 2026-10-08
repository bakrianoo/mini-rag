from pydantic import BaseModel
from typing import Optional
class ProcessRequest(BaseModel):
    file_id : str = None
    chunk_size:Optional[int] = 100
    overlap_size:Optional[int] = 20
    reset:Optional[int] = 0