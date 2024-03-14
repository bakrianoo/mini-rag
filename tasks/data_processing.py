from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import JSONLoader
from langchain_community.document_loaders import TextLoader

from langchain.text_splitter import RecursiveCharacterTextSplitter
import pymongo
from bson import json_util
import os
import math
from .constants import TaskConstants
from .database import Database

class DataProcessing:
    def __init__(self, file_path: str, project_id: str,
                       reset: int=0, chunk_size:int=100, 
                       overlap_size:int=20):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.project_id = project_id

        self.text_splitter = RecursiveCharacterTextSplitter(
                                # Set a really small chunk size, just to show.
                                chunk_size=chunk_size,
                                chunk_overlap=overlap_size,
                                length_function=len,
                                is_separator_regex=False,
                            )

        # Load the file and get its type
        self.file_type = self.get_file_type()


    def get_file_type(self):
        file_ext = self.file_path.split(".")[-1]
        if file_ext == "csv":
            return TaskConstants.CSV
        
        if file_ext == "pdf":
            return TaskConstants.PDF

        if file_ext == "jsonl":
            return TaskConstants.JSONL
        
        if file_ext == "txt":
            return TaskConstants.TXT
    
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

        if TaskConstants.TXT:
            loader = TextLoader(
                    file_path=self.file_path,
                )

            return loader.load()

    def split_data(self, documents):
        
        if len(documents) == 0:
            return []

        return self.text_splitter.split_documents(documents)

    

