from datetime import date
from enum import Enum


class PlannerSignal(Enum):
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"

    # input checks (extract)
    NO_INPUT = "PLANNER_NO_INPUT"
    TEXT_TOO_LONG = "PLANNER_TEXT_TOO_LONG"
    FILE_TYPE_NOT_SUPPORTED = "PLANNER_FILE_TYPE_NOT_SUPPORTED"
    FILE_SIZE_INVALID = "PLANNER_FILE_SIZE_INVALID"

    # schedule
    SCHEDULE_EXTRACTED = "SCHEDULE_EXTRACTED"
    SCHEDULE_NOT_FOUND_IN_INPUT = "SCHEDULE_NOT_FOUND_IN_INPUT"
    SCHEDULE_EXTRACTION_ERROR = "SCHEDULE_EXTRACTION_ERROR"
    SCHEDULE_SAVED = "SCHEDULE_SAVED"
    SCHEDULE_FETCHED = "SCHEDULE_FETCHED"
    SCHEDULE_NOT_SAVED = "SCHEDULE_NOT_SAVED"

    # plan
    PLAN_GENERATED = "PLAN_GENERATED"
    PLAN_FETCHED = "PLAN_FETCHED"
    PLAN_NOT_CREATED_YET = "PLAN_NOT_CREATED_YET"
    PLAN_DELETED = "PLAN_DELETED"
    PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
    PLAN_INPUT_INVALID = "PLAN_INPUT_INVALID"
    PLAN_GENERATION_ERROR = "PLAN_GENERATION_ERROR"
    PLAN_GENERATION_TIMEOUT = "PLAN_GENERATION_TIMEOUT"

    SCHEDULE_DELETED = "SCHEDULE_DELETED"
    SCHEDULE_NOT_FOUND = "SCHEDULE_NOT_FOUND"
class UnappliedReason(Enum):
    """Why a part of the student's note was not applied to the plan."""

    NOT_UNDERSTOOD = "not_understood"
    SUBJECT_NOT_IN_SCHEDULE = "subject_not_in_schedule"
    NOT_ENOUGH_TIME = "not_enough_time"
    NO_STUDY_DAY = "no_study_day"


class Weekday(Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    @classmethod
    def from_date(cls, value: date) -> "Weekday":
        # date.weekday(): Monday is 0, same order as the members above
        return list(cls)[value.weekday()]
