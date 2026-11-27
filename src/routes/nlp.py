from fastapi import APIRouter, status, Request
from fastapi.responses import JSONResponse
from models.ProjectModel import ProjectModel
from controllers import NLPController , ProjectController
from models import ResponseSignal
import os
import logging
from models.CardModel import CardModel

logger = logging.getLogger(__name__)


nlp_router = APIRouter(
    prefix="/api/v1/nlp",
    tags=["api_v1", "nlp"],
)


async def get_existing_project(request: Request, project_id: int):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    return await project_model.get_project_by_id(
        project_id=project_id
    )
@nlp_router.get("/index/info/{project_id}")
async def get_project_index_info(request: Request, project_id: int):
    project = await get_existing_project(request, project_id)

    if project is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Project not found."},
        )

    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )

    collection_info = await nlp_controller.get_vector_db_collection_info(
        project=project
    )

    return JSONResponse(
        content={
            "signal": ResponseSignal.VECTORDB_COLLECTION_RETRIEVED.value,
            "collection_info": collection_info,
        }
    )
@nlp_router.delete("/index/card/{project_id}/{card_id}")
async def delete_card(request: Request, project_id: int, card_id: int):
    if card_id <= 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "A valid card_id is required."},
        )

    project = await get_existing_project(request, project_id)

    if project is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Project not found."},
        )

    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )
    collection_name = nlp_controller.create_collection_name(project_id=project.project_id)

    try:
        card_model = await CardModel.create_instance(db_client=request.app.db_client)
        result = await card_model.delete_card_data(
            project_id=project.project_id,
            card_id=card_id,
            collection_name=collection_name,
        )
    except Exception as exc:
        logger.exception("Card deletion failed (rolled back)")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"Card deletion failed: {type(exc).__name__}. Nothing was deleted."},
        )

    # Files on disk: only after the DB transaction has committed
    project_path = ProjectController().get_project_path(project_id=project.project_id)
    files_deleted, files_failed = 0, []

    for name in result.pop("asset_names"):
        file_path = os.path.join(project_path, os.path.basename(name))
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                files_deleted += 1
        except OSError:
            logger.exception("Could not remove file from disk: %s", file_path)
            files_failed.append(name)

    return JSONResponse(
        content={
            "signal": "CARD_DELETED",
            "project_id": project.project_id,
            "card_id": card_id,
            "deleted": {**result, "files": files_deleted},
            "files_failed": files_failed,
        }
    )