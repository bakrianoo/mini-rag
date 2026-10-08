from fastapi import FastAPI,APIRouter,status,Request
from fastapi.responses import JSONResponse
from models.enums.ResponseEnum import ResponseEnum
from .schemes.nlp import PushRequest,SearchRequest
from controllers.NLPController import NLPController
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
import logging
import json
logger = logging.getLogger('uvicorn.error')

nlp_router = APIRouter(
    prefix='/api/v1/nlp',
    tags=['api_v1','nlp']
)

@nlp_router.post('/index/push/{project_id}')
async def index_project(request:Request,
                        project_id:str,
                        push_request:PushRequest):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_or_create_project(project_id=project_id)

    chunk_model = await ChunkModel.create_instance(
        db_client=request.app.db_client
    )

    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser = request.app.template_parser
    )

    page = 1
    inserted_items_count = 0
    idx = 0
    while True:
        page_chunks = await chunk_model.get_project_chunks(project_id=project.id, page=page)
        
        if not page_chunks:
            break

        chunks_ids = list(range(idx,idx+len(page_chunks)))
        idx += len(page_chunks)
        is_inserted = nlp_controller.index_into_vectordb(
            project=project,
            chunks=page_chunks,
            do_reset=push_request.do_reset,
            chunks_ids=chunks_ids
        )

        if not is_inserted:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": ResponseEnum.INSERT_INTO_VECTORDB_ERROR.value
                }
            )
        
        inserted_items_count += len(page_chunks)
        page += 1
        
    return JSONResponse(
        content={
            "signal": ResponseEnum.INSERT_INTO_VECTORDB_SUCCESS.value,
            "inserted_items_count": inserted_items_count
        }
    )
    
@nlp_router.get('/index/info/{project_id}')
async def get_project_index_info(request:Request,project_id:str):
    project_model = await ProjectModel.create_instance(
            db_client=request.app.db_client
        )
    
    project = await project_model.get_or_create_project(project_id=project_id)
    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser = request.app.template_parser
    )

    collection_info = nlp_controller.get_vector_db_collection_info(project=project)
    
    return JSONResponse(
        content={
            "signal":ResponseEnum.VECTORDB_COLLECTION_RETRIEVED.value,
            "collection_info":collection_info
        }
    )

@nlp_router.post('/index/search/{project_id}')
async def search_index(request:Request,project_id:str,search_request:SearchRequest):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )
        
    project = await project_model.get_or_create_project(project_id=project_id)
    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser = request.app.template_parser
    )

    results = nlp_controller.search_vector_db_collection(
        project=project,
        text=search_request.text,
        limit=search_request.limit
    )

    if not results:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": ResponseEnum.VECTORDB_SEARCH_ERROR.value,
            }
        )

    return JSONResponse(
        content={
            "signal":ResponseEnum.VECTORDB_SEARCH_SUCCESS.value,
            "results":[result.model_dump() for result in results]
        }
    )

@nlp_router.post('/index/answer/{project_id}')
async def answer_rag(request:Request,project_id:str,search_request:SearchRequest):
    project_model = await ProjectModel.create_instance(
            db_client=request.app.db_client
        )
            
    project = await project_model.get_or_create_project(project_id=project_id)
    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser = request.app.template_parser
    )

    answer,full_prompt,chat_history = nlp_controller.answer_rag_question(
        project=project,
        query=search_request.text,
        limit=search_request.limit
    )

    if not answer:
         return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": ResponseEnum.RAG_ANSWER_ERROR.value,
            }
        )
    
    return JSONResponse(
        content={
            "signal": ResponseEnum.RAG_ANSWER_SUCCESS.value,
            "answer":answer,
            "full_prompt":full_prompt,
            "chat_history":chat_history
        }
    )