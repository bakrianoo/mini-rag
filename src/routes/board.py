import logging
import uuid
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from controllers.VisionController import VisionController
from controllers.VisionMemoryController import VisionMemoryController

logger = logging.getLogger("uvicorn.error")

board_router = APIRouter(
    prefix="/api/v1/board",
    tags=["Image Understanding"],
)

memory = VisionMemoryController()


class AskImageRequest(BaseModel):
    session_id: str
    question: str


@board_router.post("/upload/{project_id}")
async def upload_image(
    request: Request,
    project_id: int,
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Please upload an image file.")

    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(400, "The uploaded image is empty.")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Maximum image size is 10 MB.")

    session_id = session_id.strip() or str(uuid.uuid4())

    db_client = request.app.db_client
    await memory.ensure_tables(db_client)

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
        "image_id": record["image_id"],
        "description": description,
    }


@board_router.post("/ask/{project_id}")
async def ask_about_image(
    request: Request,
    project_id: int,
    body: AskImageRequest,
):
    session_id = body.session_id.strip()
    question = body.question.strip()

    if not session_id or not question:
        raise HTTPException(400, "session_id and question are required.")

    db_client = request.app.db_client
    await memory.ensure_tables(db_client)

    image = await memory.get_latest_image(
        db_client, project_id, session_id
    )

    if not image:
        raise HTTPException(
            404,
            "No image found for this project and session_id. Upload an image first.",
        )

    history = await memory.get_history(
        db_client,
        project_id,
        session_id,
        image["image_id"],
        limit=10,
    )

    await memory.save_message(
        db_client, project_id, session_id,
        image["image_id"], "user", question,
    )

    vision = VisionController()

    try:
        answer = await vision.answer_question(
            image_bytes=image["image_data"],
            image_description=image["description"],
            history=history,
            question=question,
        )
    except Exception as exc:
        logger.exception("Image question failed")
        raise HTTPException(
            502, f"Image question failed: {type(exc).__name__}"
        ) from exc

    await memory.save_message(
        db_client, project_id, session_id,
        image["image_id"], "assistant", answer,
    )

    return {
        "signal": "IMAGE_ANSWER_SUCCESS",
        "image_id": image["image_id"],
        "answer": answer,
    }
