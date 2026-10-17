"""After-class homework check-in, invoked on app opening (never a timer job).

Separate preferences, daily review state and append-only planning keep this first
version easy to evolve without changing the agent or timetable import pipeline.
"""

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field, model_validator

from app import store
from app.calendar import expand_calendar
from app.contracts import AssignmentCandidate, StrictModel
from app.db import Resource, now
from app.planner import build_plan, instant


class CheckinPreferences(StrictModel):
    enabled: bool = True
    delay_minutes: int = Field(default=30, ge=0, le=180)


class PreferencesUpdate(CheckinPreferences):
    revision: int


class HomeworkItem(StrictModel):
    content: str = Field(min_length=1, max_length=4000)
    estimated_minutes: int = Field(ge=5, le=240)
    due_at: datetime | None = None

    @model_validator(mode="after")
    def valid(self):
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("请填写作业内容")
        if self.due_at and not self.due_at.tzinfo:
            raise ValueError("截止时间必须带时区")
        return self


class CourseAnswer(StrictModel):
    course_key: str
    status: Literal["none", "homework"]
    items: list[HomeworkItem] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "homework") != bool(self.items):
            raise ValueError("有作业时请填写至少一项；没有作业时不应带作业内容")
        return self


class CheckinSubmission(StrictModel):
    revision: int
    answers: list[CourseAnswer] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique(self):
        if len({a.course_key for a in self.answers}) != len(self.answers):
            raise ValueError("同一科目不能重复提交")
        if sum(len(a.items) for a in self.answers) > 60:
            raise ValueError("每次最多保存 60 项作业")
        return self


class DraftHomeworkItem(StrictModel):
    content: str = Field(max_length=4000)
    estimated_minutes: int = Field(ge=5, le=240)
    due_at: datetime | None = None

    @model_validator(mode="after")
    def aware(self):
        if self.due_at and not self.due_at.tzinfo:
            raise ValueError("截止时间必须带时区")
        return self


class DraftAnswer(StrictModel):
    course_key: str
    status: Literal["pending", "none", "homework"]
    items: list[DraftHomeworkItem] = Field(default_factory=list, max_length=12)


class CheckinDraft(StrictModel):
    revision: int
    answers: list[DraftAnswer] = Field(max_length=50)


def review_id(owner, day):
    return str(uuid5(NAMESPACE_URL, f"after-class:{owner}:{day}"))


async def preferences(db, owner):
    rows = await store.rows(db, owner, "after_class_settings")
    if rows:
        return rows[0]
    settings = await store.settings(db, owner)
    today = now().astimezone(ZoneInfo(settings.data["timezone"])).date()
    result = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="after_class_settings",
        data={**CheckinPreferences().model_dump(), "started_on": today.isoformat()},
    )
    db.add(result)
    await db.flush()
    return result


async def day_context(db, owner, settings, day, delay):
    try:
        occurrences = expand_calendar(
            settings.data,
            [store.view(r) for r in await store.rows(db, owner, "course")],
            [r.data for r in await store.rows(db, owner, "exception")],
            day,
            day,
        )
    except ValueError as exc:
        return {"due": False, "reason": str(exc)}
    if not occurrences:
        return {"due": False, "reason": "这一天没有课程"}
    groups = {}
    for event in occurrences:
        name = event["title"].strip()
        key = str(uuid5(NAMESPACE_URL, name.casefold()))
        if key not in groups:
            groups[key] = {"key": key, "name": name, "course_id": event["course_id"]}
    available = max(instant(e["ends_at"]) for e in occurrences) + timedelta(
        minutes=delay
    )
    fingerprint = store.digest(occurrences)
    return {
        "due": now() >= available,
        "date": day.isoformat(),
        "courses": list(groups.values()),
        "available_at": available.isoformat(),
        "fingerprint": fingerprint,
        "timezone": settings.data["timezone"],
        "reason": "尚未到课后询问时间" if now() < available else "",
    }


async def open_checkin(db, owner):
    pref = await preferences(db, owner)
    if not pref.data["enabled"]:
        return {"due": False, "reason": "课后作业询问已关闭"}
    settings = await store.settings(db, owner)
    today = now().astimezone(ZoneInfo(settings.data["timezone"])).date()
    # Catch up after a closed app / overnight class; do not backfill before first use.
    first = max(date.fromisoformat(pref.data["started_on"]), today - timedelta(days=6))
    for offset in range((today - first).days + 1):
        day = first + timedelta(days=offset)
        record = await db.get(Resource, review_id(owner, day))
        if record and record.data["status"] == "completed":
            continue
        context = await day_context(
            db, owner, settings, day, pref.data["delay_minutes"]
        )
        if not context["due"]:
            if day == today:
                return context
            continue
        if record is None:
            record = Resource(
                id=review_id(owner, day),
                owner_id=owner,
                kind="after_class_review",
                data={
                    "date": day.isoformat(),
                    "status": "pending",
                    "answers": {},
                    "fingerprint": context["fingerprint"],
                    "courses": context["courses"],
                },
            )
            db.add(record)
            await db.flush()
        elif record.data["fingerprint"] != context["fingerprint"]:
            record.data = {
                **record.data,
                "fingerprint": context["fingerprint"],
                "courses": context["courses"],
            }
            record.revision += 1
        pending = [
            c for c in context["courses"] if c["key"] not in record.data["answers"]
        ]
        if not pending:
            record.data = {**record.data, "status": "completed"}
            record.revision += 1
            continue
        return {**context, "courses": pending, "review": store.view(record)}
    return {"due": False, "reason": "没有待填写的课后作业"}


async def append_homework_plan(db, owner, tasks, steps, settings):
    """Reuse the deterministic planner, preserving every existing time block.

    Plan one day at a time so existing study time is deducted from each day's
    capacity. Existing blocks are busy intervals; they are never deleted or moved.
    """
    clock = now()
    tz = ZoneInfo(settings.data["timezone"])
    start = clock.astimezone(tz).date()
    occurrences = expand_calendar(
        settings.data,
        [store.view(r) for r in await store.rows(db, owner, "course")],
        [r.data for r in await store.rows(db, owner, "exception")],
        start,
        start + timedelta(days=6),
    )
    existing = await store.rows(db, owner, "plan_block")
    fixed = [r.data for r in await store.rows(db, owner, "fixed_event")]
    remaining = {s.id: s.data["estimated_minutes"] for s in steps}
    planned = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        used = sum(
            (instant(b.data["ends_at"]) - instant(b.data["starts_at"])).total_seconds()
            / 60
            for b in existing
            if instant(b.data["starts_at"]).astimezone(tz).date() == day
        )
        result = build_plan(
            {
                "now_utc": clock,
                "target_date": day.isoformat(),
                "horizon_days": 1,
                "settings": {
                    **settings.data,
                    "daily_limit_minutes": max(
                        0, settings.data["daily_limit_minutes"] - used
                    ),
                },
                "occurrences": occurrences,
                "fixed_events": fixed + [b.data for b in existing],
                "tasks": [store.view(t) for t in tasks],
                "steps": [
                    {
                        **store.view(s),
                        "data": {**s.data, "estimated_minutes": remaining[s.id]},
                    }
                    for s in steps
                ],
                "preserved_blocks": [],
                "source_revision": settings.revision,
            }
        )
        for block in result["blocks"]:
            minutes = int(
                (
                    instant(block["ends_at"]) - instant(block["starts_at"])
                ).total_seconds()
                // 60
            )
            remaining[block["step_id"]] -= minutes
            planned.append(block)
    unscheduled = []
    by_task = {t.id: t.data for t in tasks}
    for step in steps:
        if remaining[step.id] > 0:
            task = by_task[step.data["task_id"]]
            reason = "未来 7 天的可用学习时间不足，或截止前没有足够空档"
            if task["due_at"] and instant(task["due_at"]) < clock:
                reason = "截止时间已过，请在待办中设置补救截止时间后重新规划"
            unscheduled.append(
                {
                    "task_id": step.data["task_id"],
                    "title": task["title"],
                    "remaining_minutes": remaining[step.id],
                    "reason": reason,
                }
            )
    for block in planned:
        db.add(
            Resource(
                id=block["id"],
                owner_id=owner,
                kind="plan_block",
                data={k: v for k, v in block.items() if k != "id"},
            )
        )
    return {"blocks": planned, "unscheduled": unscheduled}


async def submit_checkin(db, owner, rid, body):
    record = await store.owned(db, owner, rid, "after_class_review")
    store.revision(record, body.revision)
    if record.data["status"] != "pending":
        raise HTTPException(409, "这一天已经填写完成，请在待办中修改作业")
    pref = await preferences(db, owner)
    if not pref.data["enabled"]:
        raise HTTPException(409, "课后作业询问已关闭")
    settings = await store.settings(db, owner)
    context = await day_context(
        db,
        owner,
        settings,
        date.fromisoformat(record.data["date"]),
        pref.data["delay_minutes"],
    )
    if not context["due"] or context["fingerprint"] != record.data["fingerprint"]:
        raise HTTPException(409, "课表或提醒时间已更新，请重新打开课后询问")
    courses = {c["key"]: c for c in context["courses"]}
    answers = dict(record.data["answers"])
    tasks, steps = [], []
    for answer in body.answers:
        if answer.course_key not in courses or answer.course_key in answers:
            raise HTTPException(409, "科目已填写或不属于当天课程，请重新打开课后询问")
        course = courses[answer.course_key]
        ids = []
        for item in answer.items:
            candidate = AssignmentCandidate(
                title=f"{course['name']} · {item.content.splitlines()[0]}"[:200],
                course_id=course["course_id"],
                requirements=[item.content],
                due_at=item.due_at,
                uncertain_fields=[] if item.due_at else ["due_at"],
            ).model_dump(mode="json")
            task = Resource(
                id=str(uuid4()),
                owner_id=owner,
                kind="task",
                data={
                    **candidate,
                    "status": "open",
                    "asset_id": None,
                    "remedy_due_at": None,
                    "after_class_review_id": rid,
                },
            )
            step = Resource(
                id=str(uuid4()),
                owner_id=owner,
                kind="step",
                data={
                    "key": "homework",
                    "title": "完成作业",
                    "description": item.content,
                    "estimated_minutes": item.estimated_minutes,
                    "dependency_keys": [],
                    "dependency_ids": [],
                    "acceptance_criteria": ["完成并检查所填写的作业内容"],
                    "task_id": task.id,
                    "status": "open",
                    "spent_minutes": 0,
                },
            )
            db.add(task)
            db.add(step)
            tasks.append(task)
            steps.append(step)
            ids.append(task.id)
        answers[answer.course_key] = {"status": answer.status, "task_ids": ids}
    await db.flush()
    try:
        plan = (
            await append_homework_plan(db, owner, tasks, steps, settings)
            if tasks
            else {"blocks": [], "unscheduled": []}
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    complete = set(courses) <= set(answers)
    record.data = {
        **record.data,
        "answers": answers,
        "status": "completed" if complete else "pending",
    }
    record.revision += 1
    await store.bump(db, owner)
    await db.flush()
    return {
        "review": store.view(record),
        "task_ids": [t.id for t in tasks],
        **plan,
        "timezone": settings.data["timezone"],
        "complete": complete,
    }


def after_class_router(get_db, current_user):
    router = APIRouter(prefix="/api/after-class", tags=["after-class"])

    @router.get("/preferences")
    async def get_preferences(user=Depends(current_user), db=Depends(get_db)):
        return store.view(await preferences(db, str(user.id)))

    @router.put("/preferences")
    async def update_preferences(
        body: PreferencesUpdate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            pref = await preferences(db, owner)
            store.revision(pref, body.revision)
            pref.data = {**pref.data, **body.model_dump(exclude={"revision"})}
            pref.revision += 1
            return store.view(pref)

        return await store.mutate(
            db, owner, "after-class-preferences", key, body.model_dump(), op
        )

    @router.post("/open")
    async def open_review(user=Depends(current_user), db=Depends(get_db)):
        # An opening is safe to repeat; the daily row has a deterministic identity.
        return await open_checkin(db, str(user.id))

    @router.post("/{rid}/submit")
    async def submit(
        rid: str,
        body: CheckinSubmission,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            return await submit_checkin(db, owner, rid, body)

        return await store.mutate(
            db,
            owner,
            f"after-class-submit:{rid}",
            key,
            body.model_dump(mode="json"),
            op,
        )

    @router.put("/{rid}/draft")
    async def save_draft(
        rid: str,
        body: CheckinDraft,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            record = await store.owned(db, owner, rid, "after_class_review")
            store.revision(record, body.revision)
            keys = {c["key"] for c in record.data["courses"]} - set(
                record.data["answers"]
            )
            if record.data["status"] != "pending" or any(
                a.course_key not in keys for a in body.answers
            ):
                raise HTTPException(409, "科目已更新，请重新打开课后询问")
            record.data = {
                **record.data,
                "draft_answers": [a.model_dump(mode="json") for a in body.answers],
            }
            record.revision += 1
            return store.view(record)

        return await store.mutate(
            db, owner, f"after-class-draft:{rid}", key, body.model_dump(mode="json"), op
        )

    return router
