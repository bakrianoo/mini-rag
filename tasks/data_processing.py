from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import JSONLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from .constants import TaskConstants
import pymongo
from bson import json_util
import os
import math

class DataProcessing:
    def __init__(self, file_path, project_id, reset: int=0, chunk_size:int=100, overlap_size:int=20):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.project_id = project_id

        # Load the file and get its type
        self.file_type = self.get_file_type()

        self.text_splitter = RecursiveCharacterTextSplitter(
                                # Set a really small chunk size, just to show.
                                chunk_size=chunk_size,
                                chunk_overlap=overlap_size,
                                length_function=len,
                                is_separator_regex=False,
                            )

        self.db_name = os.getenv("MONGO_DB", "mini_rag")
        self.db_chunks_collection_name = os.getenv("MONGO_CHUNKS_COLLECTION", "chunks")

        self.db_conn = None
        if os.getenv("MONGO_URI"):
            conn_uri = os.getenv("MONGO_URI")
            self.db_conn = pymongo.MongoClient(conn_uri)

            _ = self.init_db_chunks_collection()

            if reset:
                _ = self.reset_project_documents()

    def get_file_type(self):
        file_ext = self.file_path.split(".")[-1]
        if file_ext == "csv":
            return TaskConstants.CSV
        
        if file_ext == "pdf":
            return TaskConstants.PDF

        if file_ext == "jsonl":
            return TaskConstants.JSONL

    def reset_project_documents(self):
        if self.db_conn is None:
            return False

        db = self.db_conn[self.db_name]
        chunks_collection = db[self.db_chunks_collection_name]

        result = chunks_collection.delete_many({
                                                    "project_id": str(self.project_id),
                                                    "file_name": self.file_name
                                               })

        return result.deleted_count
    
    def load_data(self):

        if self.file_type == TaskConstants.CSV:
            loader = CSVLoader(self.file_path)
            return loader.load()

        if self.file_type == TaskConstants.PDF:
            loader = PyPDFLoader(self.file_path)
            return loader.load()

        if self.file_type == TaskConstants.JSONL:
            loader = JSONLoader(
                    file_path=self.file_path,
                    text_content=False,
                    json_lines=True
                )

            return loader.load()

    def split_data(self, documents):
        
        if len(documents) == 0:
            return []

        return self.text_splitter.split_documents(documents)

    def init_db_chunks_collection(self):
        # check if the collection not exists
        if self.db_conn is None:
            return False

        db = self.db_conn[self.db_name]

        if self.db_chunks_collection_name not in db.list_collection_names():
            # create the collection with index to project_id field
            chunks_collection = db[self.db_chunks_collection_name]
            chunks_collection.create_index("project_id")
            chunks_collection.create_index("file_name")

        return True

    def save_to_db(self, chunks, insert_size:int=50):
        if self.db_conn is None:
            return False

        db = self.db_conn[self.db_name]

        chunks_collection = db[self.db_chunks_collection_name]

        # Insert the chunks in batches
        inserted_docs = 0
        for i in range(0, len(chunks), insert_size):
            docs = [ 
                      { 
                        "project_id": str(self.project_id),
                        "file_name": self.file_name,
                         **dict(d)
                       } 
                      for d in chunks[i:i+insert_size] 
                   ]
            chunks_collection.insert_many(docs)
            inserted_docs += len(docs)

        return inserted_docs

    def get_project_documents(self, page:int=1, limit:int=50):
        if self.db_conn is None:
            return []

        db = self.db_conn[self.db_name]

        chunks_collection = db[self.db_chunks_collection_name]

        where_condition = {"project_id": str(self.project_id)}
        if self.file_name:
            where_condition["file_name"] = self.file_name

        total_docs = chunks_collection.count_documents(where_condition)
        
        if total_docs == 0:
            return []

        page = max(1, page)
        skip = (page - 1) * limit

        total_pages = math.ceil(total_docs / limit)

        if page > total_pages:
            return []

        docs = chunks_collection.find(where_condition, projection={'_id': False}).skip(skip).limit(limit)

        return {
            "docs": list(docs),
            "total_docs": total_docs,
            "total_pages": total_pages,
            "current_page": page
        }

