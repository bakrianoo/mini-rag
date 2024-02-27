from fastapi import FastAPI, UploadFile, HTTPException, Depends, APIRouter
from .schemes import ProcessRequest, BrowseDataRequest
from tasks import DataProcessing

from pydantic import BaseModel
from typing import Optional
from fastapi import FastAPI, File, UploadFile
import random
import string
import mimetypes
import os

data_router = APIRouter(
    prefix="/data",
    tags=["data"],
    responses={404: {"description": "Not found"}},
)

def get_unique_file_name(file_name: str, project_id: str, k=10):
    file_ext = file_name.split(".")[-1]
    file_name = project_id + "_" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=k)) + "." + file_ext
    return file_name

def get_project_path(project_id: str):
    storage_path = os.path.join(os.getcwd(), os.getenv("STORAGE_PATH", "storage"))
    project_path = os.path.join(storage_path, project_id)
    return project_path

@data_router.get("/")
async def read_data():
    app_name = os.getenv("APP_NAME")
    return {"data": "Data returned successfully" + app_name}

@data_router.post("/upload/{project_id}")
async def upload_data(project_id: str, file: UploadFile):
    
    allowed_extensions = [ e.strip() for e in os.getenv("ALLOWED_FILE_TYPES", "").split(",") if e.strip() != "" ]
    max_file_size = int(os.getenv("MAX_FILE_SIZE", 2000000))

    if file.content_type not in allowed_extensions:
        raise HTTPException(status_code=400, detail="File type not allowed")

    if file.size > max_file_size:
        raise HTTPException(status_code=400, detail="File size too large")

    # create project folder if not exists
    project_path = get_project_path(project_id)

    if not os.path.exists(project_path):
        os.makedirs(project_path)

    # create unique file name
    file_ext = file.filename.split(".")[-1]
    
    file_name = get_unique_file_name(file.filename, project_id)
    while os.path.exists(os.path.join(project_path, file_name)):
        file_name = get_unique_file_name(file.filename, project_id)

    file_path = os.path.join(project_path, file_name)

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    return {"file_name": file_name}


@data_router.post("/process/{project_id}")
async def process_data(project_id: str, req: ProcessRequest):

    file_name = req.file_name
    chunk_size = req.chunk_size
    overlab_size = req.overlab_size
    reset = req.reset

    project_path = get_project_path(project_id)

    file_path = os.path.join(project_path, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    data_processing = DataProcessing(file_path=file_path,
                                     project_id=project_id,
                                     reset=reset,
                                     chunk_size=chunk_size,
                                     overlap_size=overlab_size)

    # load into documents
    documents = data_processing.load_data()

    if len(documents) == 0:
        raise HTTPException(status_code=400, detail="Error loading data")

    # split the documents into chunks
    chunks = data_processing.split_data(documents)

    # save the chunks to the database
    inserted_docs = data_processing.save_to_db(chunks)
    if not inserted_docs:
        raise HTTPException(status_code=400, detail="Error saving to database")

    return {"inserted_docs": inserted_docs}

@data_router.post("/browse/{project_id}/{page}")
async def browse_data(project_id: str, page: int, req: BrowseDataRequest):

    file_name = req.file_name
    limit = req.limit

    project_path = get_project_path(project_id)

    file_path = os.path.join(project_path, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    data_processing = DataProcessing(file_path=file_path,
                                     project_id=project_id)

    # get the documents from the database
    documents = data_processing.get_project_documents(page=page, limit=limit)
    return {"documents": documents}
