from pydantic import BaseModel
from typing import Optional
from fastapi import UploadFile
import os

class ProcessRequest(BaseModel):
    file_name: str
    chunk_size: Optional[int] = 100
    overlab_size: Optional[int] = 20
    reset: Optional[int] = 0
    llm_type: Optional[str] = "huggingface"
