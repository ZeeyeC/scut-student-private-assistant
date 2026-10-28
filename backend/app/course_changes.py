"""One occurrence at a time: reviewed move/cancel/restore, with durable history."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field, model_validator

from app import imports, store
from app.calendar import expand_calendar
from app.contracts import ResourceView, StrictModel
from app.db import Resource, now
from app.planning_history import record_change


class CourseChange(StrictModel):
    course_id: str
    original_date: date
    action: Literal["move", "cancel", "restore"]
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def interval(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("请填写调整依据，例如教师通知")
        if self.action == "move":
            if (
                not self.starts_at
                or not self.ends_at
                or not self.starts_at.tzinfo
                or not self.ends_at.tzinfo
            ):
                raise ValueError("调课需要明确、带时区的起止时间")
            duration = self.ends_at.astimezone(
                timezone.utc
            ) - self.starts_at.astimezone(timezone.utc)
            if not 0 < duration.total_seconds() <= 86400:
                raise ValueError("课程结束必须晚于开始，单次不超过24小时")
        elif (
            self.starts_at is not None
            or self.ends_at is not None
            or self.location is not None
        ):
            raise ValueError("停课或恢复原课不应包含新时间或地点")
        return self


async def matching(db, owner, cid, original):
    return [
        r
        for r in await store.rows(db, owner, "exception")
        if r.data["course_id"] == cid and r.data["date"] == original
    ]


async def preview(db, owner, payload):
    from app.schedule import calendar_events

    p = CourseChange.model_validate(payload)
    settings = await store.settings(db, owner)
    course = await store.owned(db, owner, p.course_id, "course")
    try:
        base = expand_calendar(
            settings.data, [store.view(course)], [], p.original_date, p.original_date
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not base:
        raise HTTPException(422, "原日期没有这门课程，请选择原课表中的某一次课程")
    rows = await matching(db, owner, p.course_id, p.original_date.isoformat())
    active = [r for r in rows if r.data.get("active", True)]
    if p.action == "restore" and not active:
        raise HTTPException(422, "这次课程没有需要撤销的调整")
    before = None if active and active[-1].data.get("cancelled") else base[0]
    if active and not active[-1].data.get("cancelled"):
        e = active[-1].data
        before = {
            **base[0],
            "starts_at": e.get("starts_at") or base[0]["starts_at"],
            "ends_at": e.get("ends_at") or base[0]["ends_at"],
            "location": e["location"]
            if e.get("location") is not None
            else base[0].get("location"),
        }
    after = None if p.action == "cancel" else base[0]
    if p.action == "move":
        tz = ZoneInfo(settings.data["timezone"])
        if abs((p.starts_at.astimezone(tz).date() - p.original_date).days) > 366:
            raise HTTPException(422, "单次调课与原课程日期的间隔不能超过一年")
        after = {
            **base[0],
            "starts_at": p.starts_at.isoformat(),
            "ends_at": p.ends_at.isoformat(),
            "location": p.location
            if p.location is not None
            else base[0].get("location"),
        }
    conflicts, affected = [], []
    for label, event in [("before", before), ("after", after)]:
        if not event:
            continue
        tz = ZoneInfo(settings.data["timezone"])
        a, b = (
            datetime.fromisoformat(event["starts_at"]),
            datetime.fromisoformat(event["ends_at"]),
        )
        agenda = await calendar_events(
            db, owner, a.astimezone(tz).date(), b.astimezone(tz).date()
        )
        if agenda["warnings"]:
            raise HTTPException(
                422, "请先补齐课表配置：" + "；".join(agenda["warnings"])
            )
        for other in agenda["events"]:
            if other["id"] == base[0]["id"]:
                continue
            if a < datetime.fromisoformat(
                other["ends_at"]
            ) and b > datetime.fromisoformat(other["starts_at"]):
                if other["kind"] == "plan_block" and other["id"] not in {
                    e["id"] for e in affected
                }:
                    affected.append(other)
                if label == "after":
                    conflicts.append(other)
    return {
        "timezone": settings.data["timezone"],
        "course": store.view(course),
        "original": base[0],
        "before": before,
        "after": after,
        "conflicts": conflicts,
        "affected_plans": affected,
        "exception_versions": {r.id: r.revision for r in rows},
        "message": "只调整这一次课程。已保存学习安排、完成记录和锁定项保持原样；如受影响，请重新生成计划并确认。",
    }


async def save_change(db, owner, draft, payload):
    if store.digest(payload) != draft.data["source"].get("generated_hash"):
        raise HTTPException(422, "调整目标与预览绑定，请重新生成调整草稿")
    # Global source revision was checked by commit_draft; additionally bind the course.
    course = await store.owned(db, owner, payload["course_id"], "course")
    store.revision(course, draft.data["source"]["preview"]["course"]["revision"])
    rows = await matching(db, owner, payload["course_id"], payload["original_date"])
    if {r.id: r.revision for r in rows} != draft.data["source"]["preview"][
        "exception_versions"
    ]:
        raise HTTPException(409, "这次课程的调整已改变，请重新校对")
    before = [store.view(r) for r in rows]
    if rows:
        target = rows[0]
        target.revision += 1
    else:
        target = Resource(id=str(uuid4()), owner_id=owner, kind="exception", revision=1)
        db.add(target)
    for duplicate in rows[1:]:
        if duplicate.data.get("active", True):
            duplicate.data = {**duplicate.data, "active": False}
            duplicate.revision += 1
    target.data = {
        "course_id": payload["course_id"],
        "date": payload["original_date"],
        "cancelled": payload["action"] == "cancel",
        "starts_at": payload["starts_at"],
        "ends_at": payload["ends_at"],
        "location": payload["location"],
        "active": payload["action"] != "restore",
        "confirmed": True,
        "source": {
            "kind": "manual",
            "draft_id": draft.id,
            "reason": payload["reason"],
            "original": draft.data["source"]["preview"]["original"],
        },
        "confirmed_at": now().isoformat(),
    }
    await db.flush()
    await record_change(
        db,
        owner,
        "course_exception_changed",
        target.id,
        target.revision,
        {
            "before": before,
            "after": store.view(target),
            "action": payload["action"],
            "preview": draft.data["source"]["preview"],
        },
    )
    return [target.id]


def course_change_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/course-changes", response_model=list[ResourceView])
    async def listing(user=Depends(current_user), db=Depends(get_db)):
        return [store.view(r) for r in await store.rows(db, str(user.id), "exception")]

    @router.get("/course-change-history", response_model=list[ResourceView])
    async def history(user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(r)
            for r in await store.rows(db, str(user.id), "planning_event")
            if r.data["event_type"] == "course_exception_changed"
        ]

    @router.post("/drafts/course-change", response_model=ResourceView)
    async def draft(
        body: CourseChange,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner, payload = str(user.id), body.model_dump(mode="json")

        async def op():
            review = await preview(db, owner, payload)
            return await imports.create_draft(
                db,
                owner,
                "course_change",
                payload,
                {"preview": review, "generated_hash": store.digest(payload)},
            )

        return await store.mutate(db, owner, "course-change-draft", key, payload, op)

    return router
