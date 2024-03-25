from pydantic import BaseModel
from typing import Optional
from fastapi import UploadFile
import os

class ProcessRequest(BaseModel):
    file_name: str
    chunk_size: Optional[int] = 100
    overlab_size: Optional[int] = 20
    reset: Optional[int] = 0
    llm_embedding_type: Optional[str] = "huggingface"

class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 10
    llm_embedding_type: Optional[str] = "huggingface"
    mode: Optional[str] = "hybrid"
    hybrid_scale: Optional[float] = 0.7
    file_name: Optional[str] = None

    llm_prompt_type: Optional[str] = "openai"
    return_prompt: Optional[bool] = False
