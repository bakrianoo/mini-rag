from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, APIRouter
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import random
import string
import logging
import mimetypes
import uuid
import os
from tasks import (HTTPStatusMessage, DataProcessing, get_embedding_model, 
                  prepare_qna_prompt, get_prompt_model, get_llm_response,
                  Database, VectorStore, get_embedding)
from .schemes import ProcessRequest, SearchRequest

logger = logging.getLogger('uvicorn.error')
load_dotenv(".env")

base_router = APIRouter(
    prefix="/api/v1",
    tags=["api_v1"],
    responses={404: {"description": "Not found"}},
)

def get_project_path(project_id: str):
    project_path = os.path.join(os.getcwd(), "assets", "storage", project_id)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
    
    return project_path

def get_unique_file_name(file_name: str, project_id: str, k=10):
    random_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=k))
    file_name = f"{project_id}_{random_key}_{file_name}"
    return file_name

@base_router.get("/")
async def app_check():
    app_name = os.getenv("APP_NAME")
    return {"message": f"{app_name} is running"}


@base_router.post("/upload/{project_id}")
async def upload_data(project_id: str, file: UploadFile):
    
    allowed_extensions = [ e.strip() for e in os.getenv("ALLOWED_FILE_TYPES", "").split(",") if e.strip() != "" ]
    max_file_size = int(os.getenv("MAX_FILE_SIZE", 2000000))

    if file.content_type not in allowed_extensions:
        raise HTTPException(status_code=400, detail="File type not allowed")

    if file.size > max_file_size:
        raise HTTPException(status_code=400, detail="File size too large")

    # create project folder if not exists
    project_path = get_project_path(project_id)

    # create unique file name
    file_ext = file.filename.split(".")[-1]
    
    file_name = get_unique_file_name(file.filename, project_id)
    while os.path.exists(os.path.join(project_path, file_name)):
        file_name = get_unique_file_name(file.filename, project_id)

    file_path = os.path.join(project_path, file_name)

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    return {
        "message": HTTPStatusMessage.FILE_UPLOADED_SUCCESSFULLY,
        "data": {"file_name": file_name}
    }


@base_router.post("/process/{project_id}")
async def process_data(project_id: str, req: ProcessRequest):

    file_name = req.file_name
    chunk_size = req.chunk_size
    overlab_size = req.overlab_size
    reset = req.reset
    llm_embedding_type = req.llm_embedding_type
    batch_size = int(os.getenv("BATCH_SIZE", 10))

    project_path = get_project_path(project_id)

    file_path = os.path.join(project_path, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=HTTPStatusMessage.FILE_NOT_FOUND)

    data_processing = DataProcessing(file_path=file_path,
                                     project_id=project_id,
                                     reset=reset,
                                     chunk_size=chunk_size,
                                     overlap_size=overlab_size)

    # load into documents
    documents = data_processing.load_data()

    if not isinstance(documents, list) or len(documents) == 0:
        raise HTTPException(status_code=400, detail=HTTPStatusMessage.CAN_NOT_LOAD_FILE)

    # split the documents into chunks
    chunks = data_processing.split_data(documents)
    if not isinstance(chunks, list) or len(chunks) == 0:
        raise HTTPException(status_code=400, detail=HTTPStatusMessage.CAN_NOT_CHUNK_FILE)

    # index to vector store
    chunks_texts = [ c.page_content for c in chunks ]
    embedding_model, embedding_size = get_embedding_model(llm_embedding_type)
    vectore_store = VectorStore(
        store_dir=os.getenv("LANCEDB_DIR"),
        table_name = str(project_id)  + "_" + os.getenv("LANCEDB_DOCS_TABLE_NAME")
    )

    if reset:
        vectore_store.remove_docs(file_name=file_name)
        logger.info(f"[*RAG*] Reset the vector store for {file_name}")

    indexed_docs = 0
    for i in range(0, len(chunks_texts), batch_size):

        batch = chunks_texts[i:i+batch_size]
        vectors = get_embedding(model=embedding_model, texts=batch)
        ids = [ str(uuid.uuid4()) for d in range(len(batch)) ]

        indexed_docs += vectore_store.insert_docs(
            file_name=file_name,
            texts=batch,
            ids=ids,
            vectors=vectors
        )


    return {
        "message": HTTPStatusMessage.FILE_INDEXED_SUCCESSFULLY,
        "data": {"indexed_docs": indexed_docs}
    }


@base_router.post("/search/{project_id}")
async def search_data(project_id: str, req: SearchRequest):

    query = req.query
    top_k = req.top_k
    llm_embedding_type = req.llm_embedding_type
    mode = req.mode
    hybrid_scale = req.hybrid_scale
    file_name = req.file_name

    embedding_model, embedding_size = get_embedding_model(llm_embedding_type)

    vectore_store = VectorStore(
        store_dir=os.getenv("LANCEDB_DIR"),
        table_name = str(project_id)  + "_" + os.getenv("LANCEDB_DOCS_TABLE_NAME")
    )

    query_vector = get_embedding(model=embedding_model, texts=[query])[0]

    search_docs = vectore_store.search_docs(
        query_text=query,
        query_vector=query_vector,
        mode=mode,
        hybrid_scale=hybrid_scale,
        top_k=top_k,
        file_name=file_name
    )

    return {
        "message": HTTPStatusMessage.SEARCH_SUCCESSFULLY,
        "data": {"search_docs": search_docs}
    }

@base_router.post("/answer/{project_id}")
async def answer_query(project_id: str, req: SearchRequest):
    search_results = await search_data(project_id, req)
    search_results = search_results.get("data", {}).get("search_docs", [])

    llm_prompt_type = req.llm_prompt_type
    return_prompt = req.return_prompt

    if len(search_results) == 0:
        return {
            "message": HTTPStatusMessage.NO_RELATED_DOCUMENTS_FOUND,
            "data": {}
        }

    system_message, instructions = prepare_qna_prompt(query=req.query, documents=[doc["text"] for doc in search_results])

    client, model_id = get_prompt_model(llm_prompt_type)


    llm_response = get_llm_response(
        client=client,
        model_id=model_id,
        system_message=system_message,
        instructions=instructions
    )

    return  {
        "message": HTTPStatusMessage.LLM_ANSWER_RETURNED_SUCCESSFULLY,
        "data": {
                    "llm_prompt_type": llm_prompt_type,
                    "model_id": model_id,
                    "llm_response": llm_response,
                    "prompt": {
                                    "system_message": system_message,
                                    "instructions": instructions
                              } if return_prompt else None
                }
    }
