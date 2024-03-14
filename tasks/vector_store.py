import lancedb
import pyarrow as pa
import os
import shutil
from scipy import spatial

class VectorStore:

    def __init__(self, store_dir: str, table_name: str="docs", embedding_size: int=512):
        self.store_dir = os.path.join(os.getcwd(), store_dir)

        if not os.path.exists(self.store_dir):
            os.makedirs(self.store_dir)

        self.database = lancedb.connect(self.store_dir)
        self.table_name = table_name
        self.table = self.get_table(table_name=self.table_name, embedding_size=embedding_size)


    def get_table(self, table_name: str, embedding_size: int=512):

        if self.table_name not in self.database.table_names():

            schema = pa.schema([
                        pa.field("id", pa.string()),
                        pa.field("vector", pa.list_(pa.float32(), list_size=embedding_size)),
                        pa.field("text", pa.string()),
                        pa.field("file_name", pa.string()),
                    ])
                
            return self.database.create_table(self.table_name, schema=schema)
        
        return self.database.open_table(self.table_name)

    def insert_docs(self, file_name: str,
                          texts: list, ids: list, vectors: list):


        db_docs = [
            {
                "id": ids[i],
                "vector": vectors[i],
                "text": texts[i],
                "file_name": file_name
            }

            for i in range(len(ids))
        ]

        self.table.add(db_docs)

        # update the fts index
        self.table.create_fts_index("text", replace=True)

        return len(db_docs)

    def remove_docs(self, file_name: str=None):
        where_cond = ""
        if file_name is not None:
            where_cond = f"file_name = '{file_name}'"

        self.table.delete(where_cond)

        return True

    def search_docs(self, query_text:str,
                          query_vector: list,
                          mode:str="hybrid", # vector, text, hybrid
                          file_name: str=None,
                          hybrid_scale:float=0.7):

        where_cond = ""
        if file_name is not None:
            where_cond = f"file_name = '{file_name}'"

        if mode == "vector":
            vec_results = self.table.search(query_vector) \
                                    .where(where_cond, prefilter=True) \
                                    .metric("cosine") \
                                    .limit(top_k) \
                                    .to_list()

            return [
                    {
                        "id": doc["id"],
                        "text": doc["text"],
                        "score": 1-float(doc["_distance"]),
                        "source": "vector"
                    }
                    for doc in vec_results
                ]

        if mode == "text":
            text_results = self.table.search(query) \
                                    .where(where_cond, prefilter=True) \
                                    .limit(top_k) \
                                    .to_list()

            return [
                    {
                        "id": doc["id"],
                        "text": doc["text"],
                        "score": float(doc["score"]),
                        "source": "text"
                    }
                    for doc in fts_results
                ]

        if mode == "hybrid":

            vec_results = self.table.search(query_vector) \
                                    .where(where_cond, prefilter=True) \
                                    .metric("cosine") \
                                    .limit(top_k) \
                                    .to_list()

            text_results = self.table.search(query) \
                                    .where(where_cond, prefilter=True) \
                                    .limit(top_k) \
                                    .to_list()

            vector_scale = float(hybrid_scale)
            text_sclae = 1 - vector_scale

            vector_limit = int(top_k * vector_scale)
            text_limit = int(top_k * text_sclae)

            # combine the results
            hybrid_results = vec_results[:vector_limit] + text_results[:text_limit]

            return hybrid_results
