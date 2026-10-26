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




class ChatResponse(BaseModel):
    signal: str
    project_id: int
    conversation_id: str
    type: Literal["text", "quiz", "answer_result", "quiz_result"]
    answer: str | None = None
    quiz: dict[str, Any] | None = None
    result: dict[str, Any] | None = None

    model_config = {"exclude_none": True}


def get_chat_controller(request: Request) -> ChatController:
    return ChatController(
        db_client=request.app.db_client,
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )


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

              image = await vision_memory.get_latest_image(
               db_client=db_client,
                project_id=project_id,
               session_id=conversation_id,
                 )

                   # Reuse the existing source-selection logic.
              params = controller._extract_quiz_params(
                  body.question or "اعمل كويز"
                        )
              source = params["source"]

              has_image = bool(image and image.get("image_data"))

              if source == "image" and not has_image:
               raise HTTPException(
                status_code=404,
                detail="No image uploaded for this conversation.",
                   )

              use_image = source in ("image", "both", "auto")
              use_documents = source in ("pdf", "both", "auto")

              image_text = None

              if use_image and has_image:
               image_text = await controller.vision.analyze_image(
               image["image_data"]
                    )

              quiz = await controller.quiz.generate_quiz(
                   project=project,
                   question_count=body.question_count,
                  difficulty=body.difficulty,
                  topic=(
                       body.topic
                       if body.topic is not None
                       else params["topic"]
                                 ),
                  source_text=image_text,
                  use_documents=use_documents,
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

    image = await vision_memory.get_latest_image(
    db_client=db_client,
    project_id=project_id,
    session_id=conversation_id,
          )
    

    try:
        result = await controller.answer(
            project=project,
            question=question,
            history=history,
            image=image,
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

    if isinstance(result, dict) and result.get("type") == "quiz":
        quiz_id = result.get("quiz_id")
        questions = result.get("questions")

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
                "questions": questions,
            },
        )

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
    )