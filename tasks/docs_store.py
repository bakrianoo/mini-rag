from langchain_community.vectorstores import Chroma
from langchain_community.vectorstores import Marqo
import marqo
import os
from .llm import LLM

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
            store_path = self.settings.get("CHROMADB_DIR", "./chromadb", self.index_name)
            store_path = os.path.join(os.getcwd(), store_path)

            if self.reset_store:
                if os.path.exists(store_path):
                    os.rmdir(store_path)
            
            store = Chroma(persist_directory=store_path,
                            embedding_function=self.embedding_instance.embedding_model)
            
        elif self.store_type == "marqo":
            # check https://docs.marqo.ai/2.2.0/Guides/Models-Reference/dense_retrieval/#text
            store = marqo.Client(url=self.settings.get('marqo_url'), api_key="")
            store_all_indexes = store.get_indexes()

            existed_indes = [ index for index in store_all_indexes.get('results', []) if index['indexName'] == self.index_name]
            
            if len(existed_indes) == 0:
                store.create_index(self.index_name)
            else:
                if self.reset_store:
                    marqo_index = store.get_index(self.index_name)
                    marqo_index.delete()
                    store.create_index(self.index_name)
                
        else:
            raise ValueError(f"{self.store_type} store is not supported")

        
        return store

    def save_store_docs(self, docs, ids):
        if self.store_type == "chroma":
            store_path = self.settings.get("CHROMADB_DIR", "./chromadb")
            store_path = os.path.join(os.getcwd(), store_path)

            self.store.from_documents(docs, self.embedding_instance.embedding_model, 
                                     ids=ids,
                                     persist_directory=store_path,
                                     collection_metadata={"hnsw:space": "cosine"}
                                     )
        elif self.store_type == "marqo":
            marqo_index = self.store.get_index(self.index_name)
            _ = marqo_index.add_documents(docs)

        return True

    def search_store(self, query:str, top_k:int=3):
        if self.store_type == "chroma":
            return self.store.similarity_search_with_score(query=query, k=top_k)
        elif self.store_type == "marqo":
            docsearch = Marqo(self.store, self.index_name)
            return docsearch.index(self.index_name).search(query=query, k=top_k)
        
        return None
