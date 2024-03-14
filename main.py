import os
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv(".env")
app = FastAPI()