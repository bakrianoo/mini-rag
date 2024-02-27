from fastapi import APIRouter, FastAPI

rag_router = APIRouter(
    prefix="/rag",
    tags=["rag"],
    responses={404: {"description": "Not found"}},
)

@rag_router.get("/")
async def read_data():
    return {"data": "RAG returned successfully"}
