import logging
from typing import Literal
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from models.QuizOutput import AnswerQuestionRequest
from controllers.QuizController import QuizController
from models.ProjectModel import ProjectModel

logger = logging.getLogger("uvicorn.error")

quiz_router = APIRouter(
    prefix="/api/v1/quiz",
    tags=["api_v1", "quiz"],
)


class GenerateQuizRequest(BaseModel):
    question_count: int = Field(default=5, ge=1, le=10)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    topic: str | None = None


class SubmitAnswersRequest(BaseModel):
    answers: dict[str, str]



def get_quiz_controller(request: Request):
    return QuizController(
        db_client=request.app.db_client,
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )


@quiz_router.post("/generate/{project_id}")
async def generate_quiz(
    request: Request,
    project_id: int,
    body: GenerateQuizRequest,
):
    project_model = await ProjectModel.create_instance(
    db_client=request.app.db_client
   )

    project = await project_model.get_project_by_id(
       project_id=project_id
       )

    if project is None:
     return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Project not found."},
    )

    controller = get_quiz_controller(request)


    try:
        quiz = await controller.generate_quiz(
            project=project,
            question_count=body.question_count,
            difficulty=body.difficulty,
            topic=body.topic,
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "signal": "QUIZ_GENERATED",
                "quiz": quiz,
            },
        )

    except LookupError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": "QUIZ_SOURCE_NOT_FOUND",
                "detail": str(exc),
            },
        )

    except ValueError as exc:
        logger.warning("Quiz generation validation failed: %s", exc)

        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "signal": "QUIZ_GENERATION_ERROR",
                "detail": str(exc),
            },
        )

    except Exception:
        logger.exception("Quiz generation failed")

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": "QUIZ_GENERATION_ERROR"},
        )


@quiz_router.post("/submit/{project_id}/{quiz_id}")
async def submit_quiz(
    request: Request,
    quiz_id: int,
    project_id: int,
    body: SubmitAnswersRequest,
):
    controller = get_quiz_controller(request)

    try:
        result = await controller.submit_answers(
            quiz_id=quiz_id,
            project_id= project_id,
            answers=body.answers,
        )

        if result is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"signal": "QUIZ_NOT_FOUND"},
            )

        return JSONResponse(
            content={
                "signal": "QUIZ_SUBMITTED",
                "result": result,
            }
        )

    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": "INVALID_QUIZ_ANSWERS",
                "detail": str(exc),
            },
        )

    except Exception:
        logger.exception("Quiz submission failed")

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": "QUIZ_SUBMISSION_ERROR"},
        )

@quiz_router.post("/answer/{project_id}/{quiz_id}")
async def answer_question(
    request: Request,
    quiz_id: int,
    project_id: int ,
    body: AnswerQuestionRequest,
):
    controller = get_quiz_controller(request)

    try:
        result = await controller.check_answer(
            quiz_id=quiz_id,
            question_id=body.question_id,
            project_id= project_id,
            answer=body.answer,
        )

        if result is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"signal": "QUIZ_NOT_FOUND"},
            )

        return JSONResponse(
            content={
                "signal": "ANSWER_CHECKED",
                "result": result,
            }
        )

    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": "INVALID_QUIZ_ANSWER",
                "detail": str(exc),
            },
        )

    except Exception:
        logger.exception("Quiz answer checking failed")

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": "QUIZ_ANSWER_CHECK_ERROR"},
        )