from datetime import date as Date, time as Time
from pydantic import BaseModel, Field, field_validator

from models.enums.PlannerEnums import UnappliedReason, Weekday


class ExamItem(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    exam_date: Date
    exam_time: Time | None = None

    @field_validator("subject")
    @classmethod
    def _strip_subject(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("subject can't be empty")
        return value


class UnappliedItem(BaseModel):
    """A request from the note that the plan could not follow."""

    text: str = Field(..., min_length=1, max_length=200)
    reason: UnappliedReason


class Preferences(BaseModel):
    """What we understood from the student's short note."""

    hours_per_day: float = Field(default=4.0, ge=0.5, le=12)
    rest_weekdays: list[Weekday] = Field(default_factory=list)
    start_in_days: int = Field(default=0, ge=0, le=14)  # 0 = today, 1 = tomorrow
    focus_subjects: list[str] = Field(default_factory=list)
    unapplied: list[UnappliedItem] = Field(default_factory=list)
    max_subjects_per_day: int | None = None
    @field_validator("rest_weekdays", mode="before")
    @classmethod
    def _lowercase_days(cls, value):
        if isinstance(value, list):
            return [d.strip().lower() if isinstance(d, str) else d for d in value]
        return value


class StudySession(BaseModel):
    subject: str
    hours: float = Field(..., gt=0)


class StudyDay(BaseModel):
    date: Date
    sessions: list[StudySession] = Field(..., min_length=1)


class StudyPlan(BaseModel):
    days: list[StudyDay] = Field(..., min_length=1)
