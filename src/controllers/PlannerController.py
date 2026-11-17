import asyncio
import json
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from difflib import get_close_matches

from pydantic import ValidationError

from controllers.PlanScheduler import build_plan
from controllers.VisionController import VisionController
from models.PlannerOutput import ExamItem, Preferences, StudyPlan, UnappliedItem
from models.enums.PlannerEnums import UnappliedReason

logger = logging.getLogger("uvicorn.error")

MAX_EXAMS = 15
MAX_HORIZON_DAYS = 60
PLAN_TIME_BUDGET = 200


class PlannerInputError(ValueError):
    """The saved schedule or the note can't produce a plan; the student can fix it."""


class PlannerTimeoutError(Exception):
    """Plan generation used up its time budget."""


class PlannerController:
    def __init__(self, generation_client):
        self.generation_client = generation_client
        self.vision = VisionController()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _load_json(raw):
        if not raw:
            raise ValueError("EMPTY_RESPONSE. please try again")
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("The model returned invalid JSON.") from exc

    async def _ask_json(self, prompt: str, max_tokens: int, temperature: float):
        chat_history = [
            self.generation_client.construct_prompt(
                prompt="You return only JSON that follows the requested schema.",
                role=self.generation_client.enums.SYSTEM.value,
            )
        ]
        raw = await asyncio.to_thread(
            self.generation_client.generate_text,
            prompt=prompt,
            chat_history=chat_history,
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_format="json",
        )
        return self._load_json(raw)

    # --------------------------------------------------------- extraction
    @staticmethod
    def _extract_prompt(source: str) -> str:
        return (
            f"Extract the exam schedule from the {source}.\n"
            'Return JSON: {"exams": [{"subject": "...", "exam_date": "YYYY-MM-DD", '
            '"exam_time": "HH:MM" or null}]}\n'
            "Rules:\n"
            "- Write subject names exactly as they appear.\n"
            f"- If the year is missing, use the next occurrence of that date after {date.today().isoformat()}.\n"
            "- If no time is written, use null.\n"
            '- Do not invent exams. If there is no exam schedule, return {"exams": []}.\n'
            "- Return only the JSON."
        )

    @staticmethod
    def _clean_time(value):
        if not isinstance(value, str):
            return None
        try:
            return time.fromisoformat(value.strip()).isoformat()
        except ValueError:
            return None

    def _to_exams(self, data) -> list[dict]:
        items = data.get("exams") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError("The model returned an unexpected format.")

        exams = []
        for item in items[:MAX_EXAMS]:
            try:
                if isinstance(item, dict):
                    item = {**item, "exam_time": self._clean_time(item.get("exam_time"))}
                exams.append(ExamItem.model_validate(item).model_dump(mode="json"))
            except ValidationError:
                logger.warning("Skipping invalid exam row: %s", item)

        if not exams:
            raise LookupError("No exams were found in the schedule.")

        exams.sort(key=lambda e: (e["exam_date"], e["exam_time"] or ""))
        return exams

    async def extract_from_image(self, image_bytes: bytes) -> list[dict]:
        raw = await self.vision.read_image(image_bytes, self._extract_prompt("image"))
        return self._to_exams(self._load_json(raw))

    async def extract_from_text(self, text: str) -> list[dict]:
        prompt = self._extract_prompt("text below") + f"\n\nText:\n<<<\n{text}\n>>>"
        return self._to_exams(await self._ask_json(prompt, 2000, 0.0))

    # --------------------------------------------------------------- plan
    @staticmethod
    def _strings(value, limit: int) -> list[str]:
        """Up to `limit` non-empty strings from a list; anything else gives []."""
        if not isinstance(value, list):
            return []
        items = [v.strip() for v in value if isinstance(v, str) and v.strip()]
        return items[:limit]

    async def parse_note(self, note: str, subjects: list[str]) -> Preferences:
        note = (note or "").strip()
        if not note:
            return Preferences()

        prompt = (
            "A student wrote a short note about how they want to study (Arabic or English).\n"
            'Return JSON: {"hours_per_day": number, "start_in_days": number, "rest_weekdays": ["friday"], '
            '"focus_subjects": ["EDF108"], "unapplied": ["difficult subjects"]}\n'
            "Rules:\n"
            "- Include hours_per_day only if the note gives study hours per day.\n"
            "- Include start_in_days only if the student wants to start later than today "
            "(tomorrow = 1, the day after tomorrow = 2).\n"
            "- rest_weekdays: lowercase English weekday names the student can't or won't study.\n"
            "- focus_subjects: subjects the student wants more study time for. "
            "Match the student's mention to the closest subject in the list even if there is a small typo, missing letter, partial name, or if the student wrote only the name or only the code. "
            "Always return the exact official name from the list. "
            "Only if no reasonable match exists, return the name exactly as the student wrote it. "
            f"Official subjects: {', '.join(subjects)}.\n"
            "- unapplied: short phrases from the note that ask for something else, for example "
            "'difficult subjects' when no subject is named. Ignore greetings and thanks.\n"
            "- Return only the JSON.\n\n"
            f"Note:\n<<<\n{note}\n>>>"
        )
        data = await self._ask_json(prompt, 500, 0.0)
        if not isinstance(data, dict):
            raise PlannerInputError("Could not understand the note.")

        try:
            prefs = Preferences.model_validate(
                {
                    k: v
                    for k, v in data.items()
                    if v is not None and k in ("hours_per_day", "rest_weekdays", "start_in_days")
                }
            )
        except ValidationError as exc:
            raise PlannerInputError(
                "Could not understand the note (hours per day must be 0.5 to 12, and the start 0 to 14 days from today)."
            ) from exc


        known = {s.lower(): s for s in subjects}
        focus, unapplied = [], []

        for name in self._strings(data.get("focus_subjects"), 10):
          canonical = known.get(name.lower())
          if canonical is None:
            matches = get_close_matches(name.lower(), known.keys(), n=1, cutoff=0.75)

            if matches:
              canonical = known[matches[0]]

          if canonical is None:
            unapplied.append(
                UnappliedItem(text=name[:200], reason=UnappliedReason.SUBJECT_NOT_IN_SCHEDULE)
                 )
          elif canonical not in focus:
            focus.append(canonical)
        for phrase in self._strings(data.get("unapplied"), 5):
             unapplied.append(
                UnappliedItem(text=phrase[:200], reason=UnappliedReason.NOT_UNDERSTOOD)
            )

        return prefs.model_copy(update={"focus_subjects": focus, "unapplied": unapplied})

    @staticmethod
    def _unmet_focus(totals: dict[str, float], prefs: Preferences) -> list[str]:
        """Planned focus subjects that did not get more hours than the average of the other subjects."""
        others = [h for name, h in totals.items() if name not in prefs.focus_subjects]
        if not others:  # the student asked for every subject, nothing to compare against
            return []
        average = sum(others) / len(others)
        return [f for f in prefs.focus_subjects if f in totals and totals[f] <= average]

    @staticmethod
    def _effective_today(client_today: date | None) -> date:
        """The student's own date if the app sent it, otherwise the server's (UTC) date."""
        server_today = datetime.now(timezone.utc).date()
        if client_today is not None and abs((client_today - server_today).days) <= 1:
            return client_today
        return server_today

    async def generate_plan(
        self, exams: list[ExamItem], note: str = "", today: date | None = None
    ) -> dict:
        today = self._effective_today(today)
        upcoming = [e for e in exams if e.exam_date > today]
        if not upcoming:
            raise PlannerInputError("There are no upcoming exams in the saved schedule.")

        last_exam = max(e.exam_date for e in upcoming)
        if (last_exam - today).days > MAX_HORIZON_DAYS:
            raise PlannerInputError(
                f"The last exam is more than {MAX_HORIZON_DAYS} days away."
            )

        try:
            return await asyncio.wait_for(
                self._generate(upcoming, note, today), timeout=PLAN_TIME_BUDGET
            )
        except asyncio.TimeoutError as exc:
            raise PlannerTimeoutError(
                f"Plan generation took longer than {PLAN_TIME_BUDGET} seconds. Please try again."
            ) from exc

    async def _generate(self, upcoming: list[ExamItem], note: str, today: date) -> dict:
        subjects = list(dict.fromkeys(e.subject for e in upcoming))
        prefs = await self.parse_note(note, subjects)  # the only LLM call (skipped if no note)
        start = today + timedelta(days=prefs.start_in_days)

        result = build_plan(
            exams=upcoming,
            hours_per_day=prefs.hours_per_day,
            rest_weekdays=prefs.rest_weekdays,
            focus_subjects=prefs.focus_subjects,
            start=start,
        )
        if not result.days:
            raise PlannerInputError(
                "There is no study day before the exams. Check the rest days and the start day."
            )

        unapplied = list(prefs.unapplied)
        for name in dict.fromkeys(result.no_study_day):
            unapplied.append(UnappliedItem(text=name[:200], reason=UnappliedReason.NO_STUDY_DAY))
        for name in dict.fromkeys(result.no_time + self._unmet_focus(result.totals, prefs)):
            unapplied.append(UnappliedItem(text=name[:200], reason=UnappliedReason.NOT_ENOUGH_TIME))

        plan = StudyPlan.model_validate({"days": result.days}).model_dump(mode="json")
        prefs = prefs.model_copy(update={"unapplied": unapplied})
        return {"preferences": prefs.model_dump(mode="json"), "plan": plan}
