# mini-rag

This is a minimal implementation of the RAG model for question answering.

## Requirements

- Python 3.8 or later

## Installation

```bash
$ pip install -r requirements.txt

$ cp .env.example .env
```

## Usage

```bash
$ uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

## API Docs

- Swagger UI: http://localhost:5000/docs

## Postman Collection

Check `./assets/mini-rag-dev.postman_collection.json` for the Postman collection.
