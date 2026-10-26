import logging
import uuid
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from controllers.VisionController import VisionController
from controllers.VisionMemoryController import VisionMemoryController
from tasks.process_workflow import process_and_push_workflow
from controllers.DataController import DataController
from models.db_schemes import Asset
from models.enums.AssetTypeEnum import AssetTypeEnum
from models.db_schemes import AssetTypeEnum

logger = logging.getLogger("uvicorn.error")

board_router = APIRouter(
    prefix="/api/v1/board",
    tags=["Image Understanding"],
)

memory = VisionMemoryController()


@board_router.post("/upload/{project_id}")
async def upload_image(
    request: Request,
    project_id: int,
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    conversation_id: str = Form(default=""),
):

    content_type = file.content_type or ""
    filename = file.filename or "file"
    is_image = content_type.startswith("image/")
    is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

    if not (is_image or is_pdf):

      raise HTTPException(400, "Please upload an image or a PDF file.")

    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(400, "The uploaded image is empty.")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Maximum image size is 10 MB.")

    session_id = (
        session_id.strip()
        or conversation_id.strip()
        or str(uuid.uuid4())
    )

    db_client = request.app.db_client
    await memory.ensure_tables(db_client)

    if is_image:
        vision = VisionController()

        try:
            description = await vision.analyze_image(image_bytes)
        except Exception as exc:
            logger.exception("Image analysis failed")
            raise HTTPException(
                502, f"Image analysis failed: {type(exc).__name__}"
            ) from exc

        record = await memory.save_image(
            db_client=db_client,
            project_id=project_id,
            session_id=session_id,
            filename=file.filename or "image",
            mime_type=file.content_type,
            image_data=image_bytes,
            description=description,
        )

        await memory.save_message(
            db_client, project_id, session_id,
            record["image_id"], "assistant",
            "Saved image description: " + description,
        )

        return {
            "signal": "IMAGE_UPLOAD_SUCCESS",
            "project_id": project_id,
            "session_id": session_id,
            "conversation_id": session_id,
            "image_id": record["image_id"],
            "description": description,
        }

    try:
        data_controller = DataController()

        file_path, file_id = data_controller.generate_unique_filepath(
            orig_file_name=filename,
            project_id=project_id,
        )

        async with aiofiles.open(file_path, "wb") as output_file:
            await output_file.write(image_bytes)

        asset_model =  await AssetModel.create_instance(
                     db_client=db_client
                    )

        asset = Asset(
            asset_project_id=project_id,
            asset_type=AssetTypeEnum.FILE.value,
            asset_name=file_id,
            asset_size=os.path.getsize(file_path),
        )

        asset_record = await asset_model.create_asset(
            asset=asset
        )

        workflow = process_and_push_workflow.delay(
            project_id=project_id,
            file_id=asset_record.asset_id,
            chunk_size=500,
            overlap_size=50,
            do_reset=0,
        )

    except Exception as exc:
        logger.exception("PDF upload failed")
        raise HTTPException(
            status_code=500,
            detail=f"PDF upload failed: {type(exc).__name__}",
        ) from exc

    return {
        "signal": "PDF_UPLOAD_SUCCESS",
        "project_id": project_id,
        "session_id": session_id,
        "conversation_id": session_id,
        "document_id": asset_record.asset_id,
        "workflow_task_id": workflow.id,
        "status": "processing",
    }