
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from models.ProjectModel import ProjectModel

projects_router = APIRouter(
    prefix="/api/v1/projects",
    tags=["Projects"],
)


@projects_router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(request: Request):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.create_project()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "project_id": project.project_id,
            "project_uuid": str(project.project_uuid),
        },
    )
