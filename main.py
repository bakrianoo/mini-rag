from fastapi import FastAPI
from dotenv import load_dotenv
load_dotenv(".env")
from routes import base #from routes the folder import base.py

app = FastAPI()
app.include_router(base.base_router)