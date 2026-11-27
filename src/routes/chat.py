import logging
import uuid
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Request ,status 
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from controllers.ChatController import ChatController
from controllers.ChatMemoryController import ChatMemoryController
from controllers.VisionMemoryController import VisionMemoryController
from models.ProjectModel import ProjectModel
import asyncio
import json
from fastapi.responses import JSONResponse, StreamingResponse


logger = logging.getLogger("uvicorn.error")

chat_router = APIRouter(
    prefix="/api/v1/chat",
    tags=["Unified Chat"],
)

chat_memory = ChatMemoryController()
vision_memory = VisionMemoryController()



class ChatRequest(BaseModel):
    question: str | None = Field(default=None, max_length=10000)    
    conversation_id: str | None = None
    action: Literal[
        "chat",
        "generate_quiz",
        "answer_question",
        "submit_quiz",
    ] = "chat"


    quiz_id: int | None = None
    question_id: str | None = None
    answer: Literal["A", "B", "C", "D"] | None = None
    answers: dict[str, Literal["A", "B", "C", "D"]] | None = None
    question_count: int = Field(default=5, ge=1, le=20)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    topic: str | None = Field(default=None, max_length=500)
    card_id: int = Field(..., gt=0)
    stream: bool = False



class ChatResponse(BaseModel):
    signal: str
    project_id: int
    conversation_id: str
    type: Literal["text", "quiz", "answer_result", "quiz_result"]
    answer: str | None = None
    quiz: dict[str, Any] | None = None
    result: dict[str, Any] | None = None

    model_config = {"exclude_none": True}

    result: dict[str, Any] | None = None
    sources: list[dict[str, Any]] | None = None

def get_chat_controller(request: Request) -> ChatController:
    return ChatController(
        db_client=request.app.db_client,
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )

async def _sse_events(generate):
    """Run generate(on_token) and yield its tokens + final response as SSE."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_token(piece: str):
        # generate_text runs in a worker thread
        loop.call_soon_threadsafe(queue.put_nowait, ("token", piece))

    async def run():
        try:
            response = await generate(on_token)
            await queue.put(("done", response.model_dump()))
        except HTTPException as exc:
            await queue.put(("error", exc.detail))
        except Exception:
            logger.exception("Streaming chat failed.")
            await queue.put(("error", "Chat generation failed. Please try again."))

    task = asyncio.create_task(run())
    while True:
        event, data = await queue.get()
        yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        if event in ("done", "error"):
            break
    await task


@chat_router.post("/{project_id}", response_model=ChatResponse)
async def chat(
    project_id: int,
    body: ChatRequest,
    request: Request,
    controller: ChatController = Depends(get_chat_controller),
):
    db_client = request.app.db_client

    conversation_id = (
        body.conversation_id.strip()
        if body.conversation_id and body.conversation_id.strip()
        else str(uuid.uuid4())
    )

    question = (body.question or "").strip()

    if body.action == "chat" and not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    project_model = await ProjectModel.create_instance(
    db_client=db_client
        )  

    project = await project_model.get_project_by_id(
    project_id=project_id
      )

    if project is None:
       raise HTTPException(
        status_code=404,
        detail="Project not found.",
        )
    if body.action != "chat":
        if body.quiz_id is not None and body.quiz_id < 1:
            raise HTTPException(status_code=400, detail="Invalid quiz_id.")

        try:
            if body.action == "generate_quiz":
                await vision_memory.ensure_tables(db_client)

                params = controller._extract_quiz_params(body.question or "اعمل كويز")
                source = params["source"]

                card_images = await vision_memory.get_card_images(
                    db_client=db_client, project_id=project_id, card_id=body.card_id,
                )
                has_image = bool(card_images)

                if source == "image" and not has_image:
                    raise HTTPException(404, "No image uploaded for this card.")

                use_image = source in ("image", "both", "auto")
                use_documents = source in ("pdf", "both", "auto")

                image_text = None
                if use_image and has_image:
                    image_text = "\n\n".join(
                        i["description"] for i in card_images if i.get("description")
                    )

                quiz = await controller.quiz.generate_quiz(
                    project=project,
                    question_count=body.question_count,
                    difficulty=body.difficulty,
                    topic=(body.topic if body.topic is not None else params["topic"]),
                    source_text=image_text,
                    use_documents=use_documents,
                    card_id=body.card_id,
                )


                return ChatResponse(
                    signal="CHAT_QUIZ_SUCCESS",
                    project_id=project_id,
                    conversation_id=conversation_id,
                    type="quiz",
                    quiz={
                        "quiz_id": quiz["quiz_id"],
                        "question_count": quiz["question_count"],
                        "difficulty": quiz["difficulty"],
                        "questions": quiz["questions"],
                    },
                )

            if body.quiz_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="quiz_id is required for this action.",
                )

            if body.action == "answer_question":
                if not body.question_id or body.answer is None:
                    raise HTTPException(
                        status_code=400,
                        detail="question_id and answer are required.",
                    )

                result = await controller.quiz.check_answer(
                    quiz_id=body.quiz_id,
                    project_id=project_id,
                    question_id=body.question_id,
                    answer=body.answer,
                )

                if result is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Quiz not found.",
                    )

                return ChatResponse(
                    signal="QUIZ_ANSWER_CHECKED",
                    project_id=project_id,
                    conversation_id=conversation_id,
                    type="answer_result",
                    result=result,
                )

            if body.action == "submit_quiz":
                if body.answers is None:
                    raise HTTPException(
                        status_code=400,
                        detail="answers is required.",
                    )

                result = await controller.quiz.submit_answers(
                    quiz_id=body.quiz_id,
                    project_id=project_id,
                    answers=body.answers,
                    
                )

                if result is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Quiz not found.",
                    )

                return ChatResponse(
                    signal="QUIZ_SUBMITTED",
                    project_id=project_id,
                    conversation_id=conversation_id,
                    type="quiz_result",
                    result=result,
                )

        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc
        except LookupError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            logger.exception("Quiz action failed: %s", body.action)
            raise HTTPException(
                status_code=502,
                detail="Quiz operation failed. Please try again.",
            ) from exc

    # Existing chat flow: keep history, image context, and auto quiz detection.
    await chat_memory.ensure_tables(db_client)
    await vision_memory.ensure_tables(db_client)
    



    history = await chat_memory.get_history(
        db_client=db_client,
        project_id=project_id,
        conversation_id=conversation_id,
        limit=10,
    )

    image = await vision_memory.get_latest_project_image(
        db_client=db_client, project_id=project_id, card_id=body.card_id,
    )
    card_images = await vision_memory.get_card_images(
        db_client=db_client, project_id=project_id, card_id=body.card_id,
    )
    image_descriptions = "\n\n".join(
        i["description"] for i in card_images if i.get("description")
    )

    async def generate(on_token=None) -> ChatResponse:
        try:
            result = await controller.answer(
                project=project,
                question=question,
                history=history,
                image=image,
                card_id=body.card_id,
                image_descriptions=image_descriptions,
                on_token=on_token,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            logger.warning("Chat validation error: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            logger.warning("Chat lookup error: %s", exc)
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unified chat failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="Chat generation failed. Please try again.",
            ) from exc

        if isinstance(result, dict) and "quiz_id" in result and "questions" in result:
            quiz_id = result["quiz_id"]
            questions = result["questions"]

            if not quiz_id or not isinstance(questions, list) or not questions:
                raise HTTPException(
                    status_code=502,
                    detail="Invalid quiz response from generator.",
                )

            await chat_memory.save_message(
                db_client, project_id, conversation_id, "user", question
            )
            await chat_memory.save_message(
                db_client,
                project_id,
                conversation_id,
                "assistant",
                f"[Quiz generated: {quiz_id}]",
            )

            return ChatResponse(
                signal="CHAT_QUIZ_SUCCESS",
                project_id=project_id,
                conversation_id=conversation_id,
                type="quiz",
                quiz={
                    "quiz_id": quiz_id,
                    "question_count": result.get("question_count", len(questions)),
                    "difficulty": result.get("difficulty"),
                    "questions": questions,
                },
            )
        sources = []
        if isinstance(result, dict) and "answer" in result:
            sources = result.get("sources") or []
            result = result["answer"]

        if not isinstance(result, str) or not result.strip():
            raise HTTPException(
                status_code=502,
                detail="The model returned an empty answer.",
            )

        await chat_memory.save_message(
            db_client, project_id, conversation_id, "user", question
        )
        await chat_memory.save_message(
            db_client, project_id, conversation_id, "assistant", result
        )

        return ChatResponse(
            signal="CHAT_ANSWER_SUCCESS",
            project_id=project_id,
            conversation_id=conversation_id,
            type="text",
            answer=result,
            sources=sources or None,

        )

    if not body.stream:
        return await generate()

    return StreamingResponse(
        _sse_events(generate),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )