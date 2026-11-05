import logging
import uuid
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from controllers.VisionController import VisionController
from controllers.VisionMemoryController import VisionMemoryController
from tasks.process_workflow import process_and_push_workflow
from controllers.DataController import DataController
from models.db_schemes import Asset
from models.enums.AssetTypeEnum import AssetTypeEnum
import os
import aiofiles
from models.AssetModel import AssetModel
from celery.result import AsyncResult
from celery_app import celery_app
import asyncio

logger = logging.getLogger("uvicorn.error")

board_router = APIRouter(
    prefix="/api/v1/board",
    tags=["Image Understanding"],
)

memory = VisionMemoryController()



UPLOAD_WAIT_SECONDS = 30


def _workflow_status(task_id: str) -> dict:
    outer = AsyncResult(task_id, app=celery_app)

    if outer.state == "FAILURE":
        return {"status": "failed", "detail": "Could not start processing."}

    if outer.state != "SUCCESS" or not isinstance(outer.result, dict):
        return {"status": "processing"}

    card_id = outer.result.get("card_id")
    process_task = AsyncResult(outer.result.get("process_task_id"), app=celery_app)
    push_task = AsyncResult(outer.result.get("workflow_id"), app=celery_app)

    if "FAILURE" in (process_task.state, push_task.state):
        return {"status": "failed", "card_id": card_id}
    if push_task.state == "SUCCESS":
        return {"status": "done", "card_id": card_id}
    return {"status": "processing", "card_id": card_id}
@board_router.post("/upload/{project_id}")
async def upload_image(
    request: Request,
    project_id: int,
    card_id: int = Form(1),
    file: list[UploadFile] = File(...),
    session_id: str = Form(default=""),
    conversation_id: str = Form(default=""),
):
    if not file:
        raise HTTPException(400, "No files uploaded.")

    session_id = (
        session_id.strip()
        or conversation_id.strip()
        or str(uuid.uuid4())
    )

    db_client = request.app.db_client
    await memory.ensure_tables(db_client)

    results = []

    for uploaded_file in file:
        content_type = uploaded_file.content_type or ""
        filename = uploaded_file.filename or "file"
        is_image = content_type.startswith("image/")
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")
        is_txt = content_type == "text/plain" or filename.lower().endswith(".txt")

        if not (is_image or is_pdf or is_txt):
            raise HTTPException(400, "Please upload an image, a PDF, or a TXT file.")

        image_bytes = await uploaded_file.read()

        if not image_bytes:
            raise HTTPException(400, f"File '{filename}' is empty.")

        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(413, f"File '{filename}' exceeds 10 MB limit.")

        if is_image:
            vision = VisionController()

            try:
                description = await vision.analyze_image(image_bytes)
            except Exception as exc:
                logger.exception("Image analysis failed")
                raise HTTPException(
                    502, f"Image analysis failed for '{filename}': {type(exc).__name__}"
                ) from exc

            record = await memory.save_image(
                db_client=db_client,
                project_id=project_id,
                session_id=session_id,
                filename=filename,
                mime_type=content_type,
                card_id=card_id,
                image_data=image_bytes,
                description=description,
            )

            await memory.save_message(
                db_client, project_id, session_id,
                record["image_id"], "assistant",
                "Saved image description: " + description,
                card_id
            )

            results.append({
                "type": "image",
                "signal": "IMAGE_UPLOAD_SUCCESS",
                "image_id": record["image_id"],
                "filename": filename,
                "card_id": card_id,
                "description": description,
            })

        elif is_pdf or is_txt:

            try:
                data_controller = DataController()

                file_path, file_id = data_controller.generate_unique_filepath(
                    orig_file_name=filename,
                    project_id=project_id,
                )

                async with aiofiles.open(file_path, "wb") as output_file:
                    await output_file.write(image_bytes)

                asset_model = await AssetModel.create_instance(db_client=db_client)

                asset = Asset(
                    asset_project_id=project_id,
                    asset_type=AssetTypeEnum.FILE.value,
                    asset_name=file_id,
                    card_id=card_id,
                    asset_size=os.path.getsize(file_path),
                )

                asset_record = await asset_model.create_asset(asset=asset)

                workflow = process_and_push_workflow.delay(
                    project_id=project_id,
                    file_id=asset_record.asset_id,
                    chunk_size=500,
                    overlap_size=50,
                    card_id=card_id,
                    do_reset=0,
                )

                status = "processing"
                for _ in range(UPLOAD_WAIT_SECONDS):
                    await asyncio.sleep(1)
                    current = await asyncio.to_thread(_workflow_status, workflow.id)
                    if current["status"] in ("done", "failed"):
                        status = current["status"]
                        break

                results.append({
                    "type": "pdf",
                    "signal": "PDF_UPLOAD_SUCCESS",
                    "card_id": card_id,
                    "document_id": asset_record.asset_id,
                    "filename": filename,
                    "workflow_task_id": workflow.id,
                    "status": status,
                })
            except Exception as exc:
                logger.exception("PDF upload failed")
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF upload failed for '{filename}': {type(exc).__name__}",
                ) from exc

    return {
        "project_id": project_id,
        "session_id": session_id,
        "card_id": card_id,
        "conversation_id": session_id,
        "total_files": len(results),
        "results": results,
    }

@board_router.get("/status/{task_id}")
async def get_upload_status(task_id: str):

    outer = AsyncResult(task_id, app=celery_app)


    if outer.state == "FAILURE":
        return {"status": "failed", "detail": "Could not start processing."}

    if outer.state != "SUCCESS" or not isinstance(outer.result, dict):
        return {"status": "processing"}

    card_id = outer.result.get("card_id")
    process_task = AsyncResult(outer.result.get("process_task_id"), app=celery_app)
    push_task = AsyncResult(outer.result.get("workflow_id"), app=celery_app)

    if "FAILURE" in (process_task.state, push_task.state):
        return {"status": "failed", "card_id": card_id}
    if push_task.state == "SUCCESS":
        return {"status": "done", "card_id": card_id}
    return {"status": "processing", "card_id": card_id}
