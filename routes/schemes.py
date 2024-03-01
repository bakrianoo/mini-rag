from pydantic import BaseModel
from typing import Optional
from fastapi import UploadFile
import os

class ProcessRequest(BaseModel):
    file_name: str
    chunk_size: Optional[int] = 100
    overlab_size: Optional[int] = 20
    reset: Optional[int] = 0
    store_type: Optional[str] = "chroma"
    llm_type: Optional[str] = "huggingface"
    llm_embedding_model_id: Optional[str] = os.getenv("EMBEDDING_MODEL_ID")

class BrowseDataRequest(BaseModel):
    file_name: Optional[str] = None
    limit: Optional[int] = 50

class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 10
    store_type: Optional[str] = "chroma"
    llm_type: Optional[str] = "huggingface"
    llm_embedding_model_id: Optional[str] = os.getenv("EMBEDDING_MODEL_ID")
