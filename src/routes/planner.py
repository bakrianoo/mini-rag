import logging
from datetime import date
from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from controllers.PlannerController import (
    PlannerController,
    PlannerInputError,
    PlannerTimeoutError,
)
from models.ExamEntryModel import ExamEntryModel
from models.PlannerOutput import ExamItem
from models.ProjectModel import ProjectModel
from models.StudyPlanModel import StudyPlanModel
from models.enums.PlannerEnums import PlannerSignal

logger = logging.getLogger("uvicorn.error")

planner_router = APIRouter(
    prefix="/api/v1/planner",
    tags=["api_v1", "planner"],
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 5000


class SaveScheduleRequest(BaseModel):
    exams: list[ExamItem] = Field(..., min_length=1, max_length=30)


class GeneratePlanRequest(BaseModel):
    note: str = Field(default="", max_length=500)
    # The student's local date (YYYY-MM-DD). Used only if it is within a day of the server's UTC date.
    today: date | None = None


def get_planner_controller(request: Request):
    return PlannerController(generation_client=request.app.generation_client)


def _respond(status_code: int, signal: PlannerSignal, **content):
    return JSONResponse(
        status_code=status_code,
        content={"signal": signal.value, **content},
    )


def _bad_request(signal: PlannerSignal, detail: str):
    return _respond(status.HTTP_400_BAD_REQUEST, signal, detail=detail)


def _exam_dicts(rows) -> list[dict]:
    return [
        ExamItem(
            subject=row.subject, exam_date=row.exam_date, exam_time=row.exam_time
        ).model_dump(mode="json")
        for row in rows
    ]


def _plan_payload(record) -> dict:
    return {
        "plan": record.plan,
        "preferences": {"focus_subjects": [], "unapplied": [], "start_in_days": 0, **record.preferences},
        "note": record.note,
        "is_stale": record.is_stale,
        "expires_on": record.expires_on.isoformat(),
        "updated_at": (record.updated_at or record.created_at).isoformat(),
    }


def _no_plan_payload() -> dict:
    """Same keys as _plan_payload, so the frontend always gets the same shape."""
    return {
        "plan": None,
        "preferences": None,
        "note": None,
        "is_stale": False,
        "expires_on": None,
        "updated_at": None,
    }


async def _project_not_found(request: Request, project_id: int):
    """Return a 404 response if the project doesn't exist, otherwise None."""
    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_by_id(project_id=project_id)
    if project is None:
        return _respond(
            status.HTTP_404_NOT_FOUND,
            PlannerSignal.PROJECT_NOT_FOUND,
            detail="Project not found.",
        )
    return None


@planner_router.post("/extract/{project_id}")
async def extract_schedule(
    request: Request,
    project_id: int,
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
):
    """Read an exam schedule from an image or text. Nothing is saved here."""
    not_found = await _project_not_found(request, project_id)
    if not_found is not None:
        return not_found

    text = text.strip()
    if file is None and not text:
        return _bad_request(PlannerSignal.NO_INPUT, "Send an image or text.")
    if file is not None and text:
        return _bad_request(PlannerSignal.NO_INPUT, "Send either an image or text, not both.")
    if len(text) > MAX_TEXT_CHARS:
        return _bad_request(PlannerSignal.TEXT_TOO_LONG, f"Text is limited to {MAX_TEXT_CHARS} characters.")

    controller = get_planner_controller(request)

    try:
        if file is not None:
            if not (file.content_type or "").startswith("image/"):
                return _bad_request(PlannerSignal.FILE_TYPE_NOT_SUPPORTED, "Upload an image file.")
            image_bytes = await file.read()
            if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
                return _bad_request(PlannerSignal.FILE_SIZE_INVALID, "Image must be between 1 byte and 5 MB.")
            exams = await controller.extract_from_image(image_bytes)
        else:
            exams = await controller.extract_from_text(text)

        return _respond(status.HTTP_200_OK, PlannerSignal.SCHEDULE_EXTRACTED, exams=exams)

    except LookupError as exc:
        return _bad_request(PlannerSignal.SCHEDULE_NOT_FOUND_IN_INPUT, str(exc))

    except ValueError as exc:
        logger.warning("Schedule extraction failed: %s", exc)
        return _respond(
            status.HTTP_502_BAD_GATEWAY,
            PlannerSignal.SCHEDULE_EXTRACTION_ERROR,
            detail=str(exc),
        )

    except Exception:
        logger.exception("Schedule extraction failed")
        return _respond(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            PlannerSignal.SCHEDULE_EXTRACTION_ERROR,
        )


@planner_router.put("/schedule/{project_id}")
async def save_schedule(request: Request, project_id: int, body: SaveScheduleRequest):
    """Save the reviewed schedule. It replaces the project's previous one."""
    not_found = await _project_not_found(request, project_id)
    if not_found is not None:
        return not_found

    exam_model = await ExamEntryModel.create_instance(db_client=request.app.db_client)
    rows = await exam_model.replace_project_exams(
        project_id=project_id,
        exams=[exam.model_dump() for exam in body.exams],
    )

    # The saved plan (if any) was built from the old schedule.
    plan_model = await StudyPlanModel.create_instance(db_client=request.app.db_client)
    await plan_model.mark_stale(project_id=project_id)

    return _respond(status.HTTP_200_OK, PlannerSignal.SCHEDULE_SAVED, exams=_exam_dicts(rows))


@planner_router.get("/schedule/{project_id}")
async def get_schedule(request: Request, project_id: int):
    not_found = await _project_not_found(request, project_id)
    if not_found is not None:
        return not_found

    exam_model = await ExamEntryModel.create_instance(db_client=request.app.db_client)
    rows = await exam_model.get_project_exams(project_id=project_id)

    return _respond(status.HTTP_200_OK, PlannerSignal.SCHEDULE_FETCHED, exams=_exam_dicts(rows))

@planner_router.delete("/schedule/{project_id}")
async def delete_schedule(request: Request, project_id: int):
    """Delete the saved exam schedule and the plan built from it."""
    not_found = await _project_not_found(request, project_id)
    if not_found is not None:
        return not_found

    exam_model = await ExamEntryModel.create_instance(db_client=request.app.db_client)
    deleted = await exam_model.delete_project_exams(project_id=project_id)
    if not deleted:
        return _respond(status.HTTP_404_NOT_FOUND, PlannerSignal.SCHEDULE_NOT_FOUND)

    plan_model = await StudyPlanModel.create_instance(db_client=request.app.db_client)
    await plan_model.delete_project_plan(project_id=project_id)

    return _respond(status.HTTP_200_OK, PlannerSignal.SCHEDULE_DELETED)

@planner_router.post("/generate/{project_id}")
async def generate_plan(request: Request, project_id: int, body: GeneratePlanRequest):
    """Build a study plan from the saved schedule and save it (replaces the old one)."""
    not_found = await _project_not_found(request, project_id)
    if not_found is not None:
        return not_found

    exam_model = await ExamEntryModel.create_instance(db_client=request.app.db_client)
    rows = await exam_model.get_project_exams(project_id=project_id)
    if not rows:
        return _bad_request(PlannerSignal.SCHEDULE_NOT_SAVED, "Save an exam schedule first.")

    exams = [
        ExamItem(subject=r.subject, exam_date=r.exam_date, exam_time=r.exam_time)
        for r in rows
    ]
    controller = get_planner_controller(request)

    try:
        result = await controller.generate_plan(exams=exams, note=body.note, today=body.today)

        plan_model = await StudyPlanModel.create_instance(db_client=request.app.db_client)
        record = await plan_model.save_project_plan(
            project_id=project_id,
            plan=result["plan"],
            preferences=result["preferences"],
            note=body.note.strip() or None,
            expires_on=max(e.exam_date for e in exams),
        )
        return _respond(status.HTTP_200_OK, PlannerSignal.PLAN_GENERATED, **_plan_payload(record))

    except PlannerInputError as exc:
        return _bad_request(PlannerSignal.PLAN_INPUT_INVALID, str(exc))

    except PlannerTimeoutError as exc:
        logger.warning("Plan generation timed out: %s", exc)
        return _respond(
            status.HTTP_504_GATEWAY_TIMEOUT,
            PlannerSignal.PLAN_GENERATION_TIMEOUT,
            detail=str(exc),
        )

    except ValueError as exc:
        logger.warning("Plan generation failed: %s", exc)
        return _respond(
            status.HTTP_502_BAD_GATEWAY,
            PlannerSignal.PLAN_GENERATION_ERROR,
            detail=str(exc),
        )

    except Exception:
        logger.exception("Plan generation failed")
        return _respond(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            PlannerSignal.PLAN_GENERATION_ERROR,
        )


@planner_router.get("/plan/{project_id}")
async def get_plan(request: Request, project_id: int):
    """The saved plan, or plan=null if none was created yet.
    The plan is deleted once the last exam day has passed."""
    not_found = await _project_not_found(request, project_id)
    if not_found is not None:
        return not_found

    plan_model = await StudyPlanModel.create_instance(db_client=request.app.db_client)
    record = await plan_model.get_active_plan(project_id=project_id)
    if record is None:
        return _respond(
            status.HTTP_200_OK,
            PlannerSignal.PLAN_NOT_CREATED_YET,
            **_no_plan_payload(),
            message="No study plan has been created yet.",
        )

    return _respond(status.HTTP_200_OK, PlannerSignal.PLAN_FETCHED, **_plan_payload(record))


@planner_router.delete("/plan/{project_id}")
async def delete_plan(request: Request, project_id: int):
    not_found = await _project_not_found(request, project_id)
    if not_found is not None:
        return not_found

    plan_model = await StudyPlanModel.create_instance(db_client=request.app.db_client)
    deleted = await plan_model.delete_project_plan(project_id=project_id)
    if not deleted:
        return _respond(status.HTTP_404_NOT_FOUND, PlannerSignal.PLAN_NOT_FOUND)

    return _respond(status.HTTP_200_OK, PlannerSignal.PLAN_DELETED)
