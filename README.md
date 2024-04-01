# mini-rag

This is a minimal implementation of the RAG model for question answering.

## Requirements

- Python 3.8 or later

#### Install Python using MiniConda

1) Download and install MiniConda from [here](https://docs.anaconda.com/free/miniconda/#quick-command-line-install)
2) Create a new environment using the following command:
```bash
$ conda create -n mini-rag python=3.8
```
3) Activate the environment:
```bash
$ conda activate mini-rag
```

## Installation

### Install the required packages

```bash
$ pip install -r requirements.txt
```

### Setup the environment variables

```bash
$ cp .env.example .env
```

Set your environment variables in the `.env` file. Like `OPENAI_API_KEY` value.

### Install Ollama (Optional)

1) Install Ollama from [here](https://github.com/ollama/ollama/tree/main#ollama)
2) Pull one of the models from [here](https://github.com/ollama/ollama/tree/main#model-library)

```bash
$ ollama pull dolphin-phi
```

3) (**Optional**) set the `OLLAMA_HOST` in your operating system to be `0.0.0.0`
4) Run the Ollama server 

```bash

$ ollama serve

```

5) (**Optional**) Explore the APIs [Docs](https://github.com/ollama/ollama/blob/main/docs/api.md)


## Run the FastAPI server

```bash
$ uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

## POSTMAN Collection

Download the POSTMAN collection from [/assets/mini-rag-dev.postman_collection.json](/assets/mini-rag-dev.postman_collection.json)

## API Docs

- Swagger UI: http://localhost:5000/docs

## APIs

### 1) Upload a document

```bash
curl --location --request POST 'http://localhost:5000/api/v1/upload/1' \
--form 'file=@"/C:/Users/Home/Desktop/wiki.txt"'
```

### 2) Process the document

This step includes:
1) Extracting the text from the document
   
2) Chunking the text into documents

![alt text](assets/images/1.png)

3) Indexing the documents into LanceDB
   
![alt text](assets/images/2.png)

```bash
curl --location --request POST 'http://localhost:5000/api/v1/process/1' \
--header 'Content-Type: application/json' \
--data '{
    "file_name": "1_NYAUD71QDR_wiki.txt",
    "chunk_size": 200,
    "overlab_size": 50,
    "reset": 1,
    "llm_type": "huggingface"
}'
```

### 3) Search for similar documents

This step includes:
1) Convert query text to embeddings
   
2) Search for similar documents using the embeddings / or / keywords

![alt text](assets/images/3.png)

```bash
curl --location --request POST 'http://localhost:5000/api/v1/search/1' \
--header 'Content-Type: application/json' \
--data '{
    "query": "من مخترع الة التصوير السينمائي؟",
    "llm_type": "huggingface",
    "mode": "hybrid",
    "file_name": "1_NYAUD71QDR_wiki.txt",
    "hybrid_scale": 0.7
}'
```

### 4) Get the answer
This step includes:
1) Convert query text to embeddings
   
2) Search for similar documents using the embeddings / or / keywords
   
3) Create a prompt including the query and the similar documents
   
4) Pass the prompt to the LLM model to get the answer
   
![alt text](assets/images/4.png)

```bash
curl --location --request POST 'http://localhost:5000/api/v1/answer/1' \
--header 'Content-Type: application/json' \
--data '{
    "query": "من مخترع الة التصوير السينمائي؟",
    "llm_type": "huggingface", 
    "mode": "hybrid", 
    "llm_prompt_type": "openai", 
    "return_prompt": true
}'
```