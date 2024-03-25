import pymongo
import logging
from bson import json_util

class Database:

    def __init__(self, db_connection_str: str, db_name: str):

        self.db_name = db_name
        self.db_conn = pymongo.MongoClient(db_connection_str)


    def init_chunks_collection(self, collection_name:str="chunks"):

        db = self.db_conn[self.db_name]

        if collection_name not in db.list_collection_names():
            # create the collection with index to project_id field
            chunks_collection = db[collection_name]
            chunks_collection.create_index("project_id")
            chunks_collection.create_index("file_name")

        return True

    def insert_into_collection(self, collection_name :str,
                                     texts: list,
                                     metadata: list,
                                     project_id: str=None,
                                     file_name: str=None,
                                     batch_size:int=50,
                                     reset: bool=False):

        db = self.db_conn[self.db_name]

        chunks_collection = db[collection_name]

        if reset:
            where_condition = {"project_id": str(project_id)}
            if file_name:
                where_condition["file_name"] = file_name

            _ = chunks_collection.delete_many(where_condition)
            logging.info(f"Reset {_.deleted_count} documents from {collection_name} collection.")

        # Insert the chunks in batches
        inserted_docs = 0
        for i in range(0, len(texts), batch_size):
            db_docs = [
                {
                    "text": texts[i],
                    "metadata": metadata[i],
                    "project_id": project_id,
                    "file_name": file_name
                }
                for i in range(i, i+batch_size)

            ]
            chunks_collection.insert_many(db_docs)
            inserted_docs += len(db_docs)

        # count the total number of documents in the collection
        total_docs = chunks_collection.count_documents({"project_id": project_id})
        return total_docs

    def get_collection_documents(self, collection_name :str, project_id: str, 
                                       file_name: str=None, page:int=1, limit:int=50):

        chunks_collection = self.db[collection_name]

        where_condition = {"project_id": str(project_id)}
        if file_name:
            where_condition["file_name"] = file_name

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

    def reset_collection_documents(self, collection_name :str,
                                         project_id: str, 
                                         file_name: str=None):

        chunks_collection = self.db[collection_name]

        where_condition = {"project_id": str(project_id)}
        if file_name:
            where_condition["file_name"] = file_name

        result = chunks_collection.delete_many(where_condition)

        return result.deleted_count
