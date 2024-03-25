from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from openai import OpenAI
from functools import lru_cache
import os
import logging
import time
import requests

logger = logging.getLogger('uvicorn.error')

@lru_cache(maxsize=2)
def get_embedding_model(llm_embedding_type: str):
    embedding_model, embedding_size = None, None

    logger.info(f"[*RAG*] Loading {llm_embedding_type} LLM")
    start_time = time.time()

    if llm_embedding_type == "openai":
        embedding_model = OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDING_MODEL_ID"),
                                 openai_api_key=os.getenv("OPENAI_API_KEY"))
        embedding_size = os.getenv("OPENAI_EMBEDDING_MODEL_SIZE", 1024)

    elif llm_embedding_type == "huggingface":
        embedding_model = HuggingFaceEmbeddings(
                        model_name=os.getenv("HUGGINGFACE_EMBEDDING_MODEL_ID"),
                        model_kwargs={'device': os.getenv("HUGGINGFACE_DEVICE")},
                        encode_kwargs={'normalize_embeddings': True}
                    )
        
        embedding_size = os.getenv("HUGGINGFACE_EMBEDDING_MODEL_SIZE", 1024)

    else:
        raise ValueError(f"{llm_embedding_type} LLM is not supported")

    elapsed_time = time.time() - start_time
    logger.info(f"[*RAG*] {llm_embedding_type} LLM loaded in {elapsed_time} seconds")

    return embedding_model, embedding_size

def get_prompt_model(llm_prompt_type: str):
    client, model_id = None, None
    if llm_prompt_type == "openai":
        client =  OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model_id = os.getenv("OPENAI_PROMPT_MODEL_ID")

    elif llm_prompt_type == 'ollama':
        ollama_url = os.getenv("OLLAMA_API_URL")
        client = OpenAI(base_url=ollama_url, api_key="ollama")
        model_id = os.getenv("OLLAMA_PROMPT_MODEL_ID")

    else:
        raise ValueError(f"{llm_prompt_type} LLM is not supported")

    return client, model_id

def get_embedding(model, texts: list):
    if isinstance(texts, str):
        texts = [texts]
    
    return model.embed_documents(texts)

def prepare_qna_prompt(query: str, documents: list):
    system_message = "\n".join([
        "You are an AI assistant helping a user to find the most relevant information.",
        "You will be given a user query and a list of documents.",
        "Only generate an answer if you are confident that the answer is correct.",
        "The answer must be relevant to the user query and the document content.",
        "If you are not confident, you can applogize.",
        "Replay within the same language and style as the user query.",
    ])

    instructions = "\n".join([
        "### Documents: ",
        "\n".join(documents),

        "\n",
        "### Query: ",
        query,
        "\n",
        "### Answer: ",
    ])

    return system_message, instructions

def get_llm_response(client, model_id: str, system_message: str, instructions: str):
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": instructions}
        ]
    )
    
    return response.choices[0].message.content
