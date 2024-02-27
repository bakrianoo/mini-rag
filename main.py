import uvicorn
import os
from fastapi import FastAPI
from routes import data_router, rag_router
from dotenv import load_dotenv

load_dotenv(".env")
app = FastAPI()

# initate the storage path if not exists
storage_path = os.path.join(os.getcwd(), os.getenv("STORAGE_PATH", "storage"))
if not os.path.exists(storage_path):
    os.makedirs(storage_path)

app.include_router(data_router)
app.include_router(rag_router)
