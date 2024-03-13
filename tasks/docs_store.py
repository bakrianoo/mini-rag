import chromadb
import lancedb
import pyarrow as pa
import os
import shutil
from .llm import LLM
from scipy import spatial

class DocsStore:
    def __init__(self, store_type, index_name:str, 
                 llm_type: str, llm_embedding_model_id:str,
                 reset_store: bool=False,
                 settings: dict={}):
        self.store_type = store_type
        self.llm_embedding_model_id = llm_embedding_model_id
        self.settings = settings
        self.reset_store = reset_store
        self.index_name = index_name
        self.embedding_instance = LLM(llm_type=llm_type, llm_embedding_model_id=llm_embedding_model_id)

        self.store = self.load_store()
        

    def load_store(self):
        store = None

        if self.store_type == "chroma":
            store_path = self.settings.get("CHROMADB_DIR", "./chromadb")
            store_path = os.path.join(os.getcwd(), store_path)

            if self.reset_store:
                if os.path.exists(store_path):
                    shutil.rmtree(store_path)
            
            db = chromadb.PersistentClient(path=store_path)

            self.store = db.create_collection(
                                name=self.index_name,
                                metadata={"hnsw:space": "cosine"} # l2 is the default
                            )
            
        elif self.store_type == "lancedb":
            store_path = self.settings.get("LANCEDB_DIR", "./lancedb")
            store_path = os.path.join(os.getcwd(), store_path)

            if self.reset_store:
                if os.path.exists(store_path):
                    shutil.rmtree(store_path)
            
            db = lancedb.connect(store_path)
            if self.index_name not in db.table_names():
                schema = pa.schema([
                        pa.field("vector", pa.list_(pa.float32(), list_size=512)),
                        pa.field("text", pa.string()),
                        pa.field("id", pa.string()),
                    ])
                
                self.store = db.create_table(self.index_name, schema=schema)
            else:
                self.store = db.open_table(self.index_name)

                
        else:
            raise ValueError(f"{self.store_type} store is not supported")

        
        return self.store

    def save_store_docs(self, docs, ids):

        if self.store_type == "chroma":
            text_docs = [ d.page_content for d in docs ]
            # metadata_docs = [ d.metadata for d in docs ]

            docs_embed = self.embedding_instance.get_embedding(text_docs)
            _ = self.store.add(
                documents=text_docs,
                embeddings=docs_embed,
                # metadatas=metadata_docs,
                ids=ids
            )
        
        elif self.store_type == "lancedb":
            text_docs = [ d.page_content for d in docs ]
            # metadata_docs = [ d.metadata for d in docs ]

            docs_embed = self.embedding_instance.get_embedding(text_docs)

            lance_docs = [
                {
                    "vector": docs_embed[i],
                    "text": text_docs[i],
                    "id": ids[i]
                }

                for i in range(len(docs))
            ]

            self.store.add(lance_docs)
            self.store.create_fts_index("text")

        return True

    def search_store(self, query:str, top_k:int=3, mode:str="hybrid", hybrid_scale:float=0.7):

        query_embed = self.embedding_instance.get_embedding(query)

        if self.store_type == "chroma":
            results = self.store.query(
                query_embeddings=query_embed,
                n_results=top_k,
            )

            return results
        
        elif self.store_type == "lancedb":

            if mode == "vector":

                vec_results = self.store.search(query_embed[0]) \
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

            elif mode == "full-text":

                fts_results = self.store.search(query) \
                                    .limit(top_k) \
                                    .to_list()

                return [
                    {
                        "id": doc["id"],
                        "text": doc["text"],
                        "score": float(doc["score"]),
                        "source": "fts"
                    }
                    for doc in fts_results
                ]

            elif mode == "hybrid":

                vec_results = self.store.search(query_embed[0]) \
                                    .metric("cosine") \
                                    .limit(top_k) \
                                    .to_list()

                vec_results = [
                                    {
                                        "id": doc["id"],
                                        "text": doc["text"],
                                        "score": 1-float(doc["_distance"]),
                                        "source": "vector"
                                    }
                                    for doc in vec_results
                                ]

                vec_results_ids = set([doc["id"] for doc in vec_results])

                fts_results = self.store.search(query) \
                                    .limit(top_k) \
                                    .to_list()

                max_score = max([doc["score"] for doc in fts_results])

                fts_results =   [
                                    {
                                        "id": doc["id"],
                                        "text": doc["text"],
                                        "score": 1 - spatial.distance.cosine(query_embed[0], doc["vector"]),
                                        "source": "fts"
                                    }
                                    for doc in fts_results
                                    if doc["id"] not in vec_results_ids
                                ]

                vector_scale = float(hybrid_scale)
                fts_sclae = 1 - vector_scale

                vector_limit = int(top_k * vector_scale)
                fts_limit = int(top_k * fts_sclae)

                # combine the results
                combined_results = vec_results[:vector_limit] + fts_results[:fts_limit]

                # sort the combined results by score
                combined_results = sorted(combined_results, key=lambda x: x["score"], reverse=True)

                return combined_results

        return []
