import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from models.PlannerOutput import ExamItem
from models.enums.PlannerEnums import Weekday

FOCUS_WEIGHT = 1.5
EPS = 1e-9

"""Builds the study plan in plain Python (no LLM), so the rules always hold:

- every subject is studied on the last available day before its exam
- nothing is planned on rest days, before the start day, or on/after an exam day
- a day never goes over the student's hours
- focus subjects get a double share of the time
"""

class _Block:
    """A study block (1 hour, or 0.5 for the leftover half hour) on one day."""

    __slots__ = ("day", "hours", "subject")

    def __init__(self, day: date, hours: float):
        self.day = day
        self.hours = hours
        self.subject = None  # index of the exam this block was given to


@dataclass
class ScheduleResult:
    days: list[dict] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)  # subject -> planned hours
    no_study_day: list[str] = field(default_factory=list)  # no usable day before the exam
    no_time: list[str] = field(default_factory=list)  # had days, but every block went to others


def _day_blocks(hours_per_day: float) -> list[float]:
    blocks = [1.0] * int(hours_per_day)
    if hours_per_day - int(hours_per_day) >= 0.5:
        blocks.append(0.5)
    return blocks


def _targets(weight: dict, cap: dict, total: float) -> dict:
    """Share `total` hours by weight, never giving a subject more than it can use before its exam."""
    target, active, left = {}, set(weight), total
    while active:
        weight_sum = sum(weight[i] for i in active)
        capped = {i for i in active if left * weight[i] / weight_sum >= cap[i] - EPS}
        if not capped:
            for i in active:
                target[i] = left * weight[i] / weight_sum
            break
        for i in capped:
            target[i] = cap[i]
            left -= cap[i]
        active -= capped
        left = max(left, 0.0)
    return target


def build_plan(
    exams: list[ExamItem],
    hours_per_day: float,
    rest_weekdays: list[Weekday],
    focus_subjects: list[str],
    start: date,
    max_subjects_per_day: int | None = None,
) -> ScheduleResult:
    rest = set(rest_weekdays)
    last_exam = max(e.exam_date for e in exams)

    # 1) Study blocks on every usable day from `start` to the day before the last exam.
    blocks, by_day = [], defaultdict(list)
    day = start
    while day < last_exam:
        if Weekday.from_date(day) not in rest:
            for hours in _day_blocks(hours_per_day):
                block = _Block(day, hours)
                blocks.append(block)
                by_day[day].append(block)
        day += timedelta(days=1)

    # window[i] = how many blocks fall before exam i (blocks are in date order)
    window = [sum(1 for b in blocks if b.day < e.exam_date) for e in exams]
    reachable = [i for i in range(len(exams)) if window[i] > 0]

    result = ScheduleResult(
        no_study_day=[exams[i].subject for i in range(len(exams)) if window[i] == 0]
    )
    if not reachable:
        return result

    # 2) The night before each exam: give the subject a block on the last usable day
    #    before it (earlier days only if that day has no free block left).
    for i in sorted(reachable, key=lambda i: (exams[i].exam_date, i)):
        for d in sorted((d for d in by_day if d < exams[i].exam_date), reverse=True):
            free = [b for b in by_day[d] if b.subject is None]
            if free:
                max(free, key=lambda b: b.hours).subject = i
                break

    # 3) Share the rest of the time: focus subjects count double, and nobody gets more
    #    than the blocks available before their exam.
    focus = {name.lower() for name in focus_subjects}
    weight = {i: FOCUS_WEIGHT if exams[i].subject.lower() in focus else 1.0 for i in reachable}
    cap = {i: sum(b.hours for b in blocks[: window[i]]) for i in reachable}
    target = _targets(weight, cap, sum(b.hours for b in blocks))

    assigned = {i: sum(b.hours for b in blocks if b.subject == i) for i in reachable}
    remaining = {i: max(0.0, target[i] - assigned[i]) for i in reachable}

    max_per_day = max(1.0, float(math.ceil(hours_per_day / 2)))  # keep a day varied

    max_subjects = max_subjects_per_day if max_subjects_per_day and max_subjects_per_day >= 1 else None
    subjects_on_day = defaultdict(set)

    focus_idx = {i for i in reachable if weight[i] > 1.0}  # focus subjects may take one more hour
    day_used = defaultdict(float)
    for b in blocks:
        if b.subject is not None:
            day_used[(b.day, b.subject)] += b.hours

    # 4) Fill the free blocks in date order. The subject that is most behind its share
    #    compared with the time it still has before its exam goes first.
    for pos, block in enumerate(blocks):
        if block.subject is not None:
            continue

        eligible = [i for i in reachable if window[i] > pos]
        wanting = [i for i in eligible if remaining[i] > EPS]
        candidates = wanting or eligible
        roomy = [
            i
            for i in candidates
            if day_used[(block.day, i)] + block.hours
            <= max_per_day + (1.0 if i in focus_idx else 0.0) + EPS
        ]
        candidates = roomy or candidates

        if wanting:
            def urgency(i):
                free = sum(b.hours for b in blocks[pos : window[i]] if b.subject is None)
                return remaining[i] / free

            pick = max(
                candidates,
                key=lambda i: (round(urgency(i), 6), -exams[i].exam_date.toordinal(), -i),
            )
        else:
            pick = min(candidates, key=lambda i: (assigned[i] / weight[i], exams[i].exam_date, i))

        if max_subjects is not None:
         already = subjects_on_day[block.day]
         if len(already) >= max_subjects and pick not in already:
           possible = [i for i in candidates if i in already]
           if possible:
            pick = max(possible, key=lambda i: remaining[i]) if wanting else possible[0]
           else:
            continue
        block.subject = pick
        subjects_on_day[block.day].add(pick)
        assigned[pick] += block.hours
        remaining[pick] = max(0.0, remaining[pick] - block.hours)
        day_used[(block.day, pick)] += block.hours

    # 5) Output.
    sessions_by_day, totals = defaultdict(lambda: defaultdict(float)), defaultdict(float)
    for b in blocks:
        if b.subject is not None:
            sessions_by_day[b.day][b.subject] += b.hours
            totals[exams[b.subject].subject] += b.hours

    for d in sorted(sessions_by_day):
        items = sorted(sessions_by_day[d].items(), key=lambda kv: (exams[kv[0]].exam_date, kv[0]))
        result.days.append(
            {
                "date": d.isoformat(),
                "sessions": [{"subject": exams[i].subject, "hours": h} for i, h in items],
            }
        )
    result.totals = dict(totals)
    result.no_time = [exams[i].subject for i in reachable if assigned[i] <= EPS]
    return result
