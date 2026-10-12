import logging
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from controllers.ChatController import ChatController
from controllers.ChatMemoryController import ChatMemoryController
from controllers.VisionMemoryController import VisionMemoryController
from models.ProjectModel import ProjectModel

logger = logging.getLogger("uvicorn.error")

chat_router = APIRouter(
    prefix="/api/v1/chat",
    tags=["Unified Chat"],
)

chat_memory = ChatMemoryController()
vision_memory = VisionMemoryController()


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None


@chat_router.post("/{project_id}")
async def chat(project_id: int, body: ChatRequest, request: Request):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    conversation_id = (
        body.conversation_id.strip()
        if body.conversation_id and body.conversation_id.strip()
        else str(uuid.uuid4())
    )

    db_client = request.app.db_client

    await chat_memory.ensure_tables(db_client)
    await vision_memory.ensure_tables(db_client)

    project_model = await ProjectModel.create_instance(
        db_client=db_client
    )
    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )

    history = await chat_memory.get_history(
        db_client=db_client,
        project_id=project_id,
        conversation_id=conversation_id,
        limit=10,
    )

    # Images uploaded through /api/v1/board/upload/{project_id}
    # use the same value as their session_id.
    image = await vision_memory.get_latest_image(
        db_client=db_client,
        project_id=project_id,
        session_id=conversation_id,
    )

    await chat_memory.save_message(
        db_client, project_id, conversation_id, "user", question
    )

    controller = ChatController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )

    try:
        answer = await controller.answer(
            project=project,
            question=question,
            history=history,
            image=image,
        )
    except Exception as exc:
        logger.exception("Unified chat failed")
        raise HTTPException(
            status_code=502,
            detail=f"Chat generation failed: {type(exc).__name__}",
        ) from exc

    if not answer or not answer.strip():
        raise HTTPException(
            status_code=502,
            detail="The model returned an empty answer.",
        )

    await chat_memory.save_message(
        db_client, project_id, conversation_id, "assistant", answer
    )

    return {
        "signal": "CHAT_ANSWER_SUCCESS",
        "project_id": project_id,
        "conversation_id": conversation_id,
        "answer": answer,
    }
