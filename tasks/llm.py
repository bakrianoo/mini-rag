from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from functools import lru_cache
import os

@lru_cache(maxsize=2)
def get_embedding_model(llm_type: str):
    embedding_model, embedding_size = None, None

    if llm_type == "openai":
        embedding_model = OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDING_MODEL_ID"),
                                 openai_api_key=os.getenv("OPENAI_API_KEY"))
        embedding_size = os.getenv("OPENAI_EMBEDDING_MODEL_SIZE", 1024)

    elif llm_type == "huggingface":
        embedding_model = HuggingFaceEmbeddings(
                        model_name=os.getenv("HUGGINGFACE_EMBEDDING_MODEL_ID"),
                        model_kwargs={'device': os.getenv("HUGGINGFACE_DEVICE")},
                        encode_kwargs={'normalize_embeddings': True}
                    )
        
        embedding_size = os.getenv("HUGGINGFACE_EMBEDDING_MODEL_SIZE", 1024)

    else:
        raise ValueError(f"{llm_type} LLM is not supported")

    return embedding_model, embedding_size

def get_embedding(model, texts: list):
    if isinstance(texts, str):
        texts = [texts]
    
    return model.embed_documents(texts)
