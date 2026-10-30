"""Explicit T05 rules produce reviewable candidates, not inferred profiles."""

from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field, model_validator

from app import imports, store
from app.calendar import occupied_course_events
from app.constraints import local_instant, planning_constraints
from app.contracts import ResourceView, StrictModel
from app.db import Resource
from app.study_types import CourseType


class RoutineWindow(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    start: time
    end: time
    weekdays: list[int] = Field(default_factory=lambda: list(range(1, 8)), max_length=7)

    @model_validator(mode="after")
    def valid(self):
        if (
            self.end <= self.start
            or not self.weekdays
            or any(d < 1 or d > 7 for d in self.weekdays)
        ):
            raise ValueError("作息需要明确起止和有效星期；跨午夜请分成两段")
        return self


class CourseTypeRule(StrictModel):
    course_type: CourseType
    preparation_minutes: int = Field(0, ge=0, le=180, strict=True)
    review_minutes: int = Field(0, ge=0, le=180, strict=True)

    @model_validator(mode="after")
    def explicit_type(self):
        if self.course_type == "unknown":
            raise ValueError("类型规则需要明确课程类型，未知课程不套用推断规则")
        return self


class RoutineRequest(StrictModel):
    confirmed: Literal[True]
    target_date: date | None = None
    horizon_days: int = Field(7, ge=1, le=7)
    daily_windows: list[RoutineWindow] = Field(default_factory=list, max_length=8)
    preparation_minutes: int = Field(0, ge=0, le=180)
    review_minutes: int = Field(0, ge=0, le=180)
    include_campus_transfer: bool = False
    course_type_rules: list[CourseTypeRule] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique_types(self):
        if len({r.course_type for r in self.course_type_rules}) != len(
            self.course_type_rules
        ):
            raise ValueError("同一课程类型只允许一条明确规则")
        return self


class Candidate(StrictModel):
    id: str
    kind: Literal["routine", "preparation", "review", "commute"]
    title: str
    starts_at: datetime
    ends_at: datetime
    can_add: bool
    dismissed: bool
    conflicts: list[str]
    basis: dict = Field(default_factory=dict)


class RoutinePreview(StrictModel):
    schema_version: int = 1
    source_revision: int
    timezone: str
    source: Literal["explicit_request"] = "explicit_request"
    candidates: list[Candidate]
    warnings: list[str]


class CandidateDraft(StrictModel):
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_source_revision: int = Field(ge=1)
    request: RoutineRequest


async def preview_candidates(db, owner, request):
    from app.planner import instant, planning_result

    inputs, _ = await planning_result(
        db, owner, request.target_date, request.horizon_days
    )
    zone = ZoneInfo(inputs["settings"]["timezone"])
    target = date.fromisoformat(inputs["target_date"])
    lower = datetime.combine(target, time.min, zone)
    upper = lower + timedelta(days=request.horizon_days)
    dismissed = {
        r.data["candidate_id"] for r in await store.rows(db, owner, "routine_dismissal")
    }
    busy = occupied_course_events(inputs["occurrences"]) + inputs["fixed_events"]
    busy += [r["data"] for r in planning_constraints(inputs)]
    busy += inputs["current_blocks"]
    candidates = {}
    warnings = []
    from app.calendar import expand_calendar
    from app.planning_facts import active_profile

    confirmed_profile = inputs.get("profile_context", {}).get("data", {})
    interval = (
        confirmed_profile.get("preferences", {}).get("review_interval_days")
        if confirmed_profile.get("confirmed")
        else None
    )

    def add(kind, title, a, b, source, basis=None):
        if b <= lower or a >= upper:
            return
        identity = store.digest(
            {
                "kind": kind,
                "title": title,
                "starts_at": a.isoformat(),
                "ends_at": b.isoformat(),
                "source": source,
            }
        )
        conflicts = []
        if a < instant(inputs["now_utc"]):
            conflicts.append("开始时间已过去")
        for row in busy:
            if instant(a) < instant(row["ends_at"]) and instant(b) > instant(
                row["starts_at"]
            ):
                conflicts.append(
                    "与" + row.get("title", "课程、禁排或已有安排") + "重叠"
                )
        candidates[identity] = Candidate(
            id=identity,
            kind=kind,
            title=title,
            starts_at=a,
            ends_at=b,
            dismissed=identity in dismissed,
            can_add=not conflicts and identity not in dismissed,
            conflicts=list(dict.fromkeys(conflicts)),
            basis=basis or {},
        )

    try:
        for day in (target + timedelta(days=i) for i in range(request.horizon_days)):
            for window in request.daily_windows:
                if day.isoweekday() in window.weekdays:
                    add(
                        "routine",
                        window.title,
                        local_instant(datetime.combine(day, window.start), zone),
                        local_instant(datetime.combine(day, window.end), zone),
                        "explicit_daily_window",
                    )
        course_events = inputs["occurrences"]
        if (
            request.review_minutes
            or any(r.review_minutes for r in request.course_type_rules)
        ) and interval:
            course_events = expand_calendar(
                inputs["settings"],
                [store.view(r) for r in await store.rows(db, owner, "course")],
                [r.data for r in await store.rows(db, owner, "exception")],
                target - timedelta(days=interval),
                target + timedelta(days=request.horizon_days - 1),
            )
            warnings.append(
                f"复习候选采用已确认档案的{interval}天间隔；复习分钟仍由本次明确指定，保存前需校对"
            )
        courses = sorted(course_events, key=lambda e: instant(e["starts_at"]))
        for course in courses:
            a, b = instant(course["starts_at"]), instant(course["ends_at"])
            source = course.get(
                "id", course.get("course_id", course.get("title", "course"))
            )
            classification = (
                inputs.get("study_classifications", {})
                .get("course", {})
                .get(course.get("course_id"), {})
            )
            course_type = classification.get("course_type", "unknown")
            rule = next(
                (r for r in request.course_type_rules if r.course_type == course_type),
                None,
            )
            prepare_minutes = (
                rule.preparation_minutes if rule else request.preparation_minutes
            )
            review_minutes = rule.review_minutes if rule else request.review_minutes
            basis = {
                "course_type": course_type,
                "rule_source": "explicit_course_type_rule"
                if rule
                else "explicit_general_minutes",
                "classification_id": classification.get("id"),
                "classification_revision": classification.get("revision"),
            }
            if request.course_type_rules and course_type == "unknown":
                warnings.append(
                    course.get("title", "课程") + "类型未知，未猜测或套用课程类型规则"
                )
            source = f"{source}:type:{course_type}:prepare:{prepare_minutes}:review:{review_minutes}"
            if prepare_minutes:
                add(
                    "preparation",
                    course.get("title", "课程") + " · 课前准备",
                    a - timedelta(minutes=prepare_minutes),
                    a,
                    source,
                    {**basis, "minutes": prepare_minutes},
                )
            if review_minutes:
                profile = active_profile(inputs, b)
                profile_zone = ZoneInfo(profile["timezone"]) if profile else zone
                delay = profile.get("preferences", {}).get("review_interval_days") or 0
                review_start = local_instant(
                    b.astimezone(profile_zone).replace(tzinfo=None)
                    + timedelta(days=delay),
                    profile_zone,
                )
                if delay and not active_profile(inputs, review_start):
                    review_start = b
                add(
                    "review",
                    course.get("title", "课程") + " · 课后复习",
                    review_start,
                    review_start + timedelta(minutes=review_minutes),
                    f"{source}:profile:{inputs.get('profile_context', {}).get('revision', 0)}"
                    if delay
                    else source,
                    {**basis, "minutes": review_minutes},
                )
        if request.include_campus_transfer:
            matrix = {
                (t["from_campus"], t["to_campus"]): t["minutes"]
                for t in inputs["settings"]["campus_transfers"]
            }
            for previous, following in zip(courses, courses[1:]):
                a, b = instant(previous["ends_at"]), instant(following["starts_at"])
                if a.astimezone(zone).date() != b.astimezone(zone).date():
                    continue
                left, right = previous.get("campus"), following.get("campus")
                if not left or not right:
                    warnings.append("课程校区未知，未猜测通勤时长")
                    continue
                if left == right:
                    continue
                minutes = matrix.get((left, right))
                if minutes is None:
                    warnings.append(f"{left}→{right}未确认转移时长，未生成通勤")
                    continue
                add(
                    "commute",
                    f"{left}→{right}校区转移",
                    b - timedelta(minutes=minutes),
                    b,
                    previous.get("id", "") + following.get("id", ""),
                )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if (
        not request.daily_windows
        and not request.preparation_minutes
        and not request.review_minutes
        and not request.course_type_rules
        and not request.include_campus_transfer
    ):
        warnings.append("未提供明确作息或准备规则，不猜测用餐、午休或课程类型")
    return RoutinePreview(
        source_revision=inputs["source_revision"],
        timezone=zone.key,
        candidates=sorted(candidates.values(), key=lambda c: (c.starts_at, c.id)),
        warnings=list(dict.fromkeys(warnings)),
    )


def routine_router(get_db, current_user):
    router = APIRouter()

    @router.post("/daily-routine-preview", response_model=RoutinePreview)
    async def preview(
        body: RoutineRequest, user=Depends(current_user), db=Depends(get_db)
    ):
        return await preview_candidates(db, str(user.id), body)

    @router.post("/daily-routine-drafts", response_model=ResourceView)
    async def draft(
        body: CandidateDraft,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            store.revision(
                await store.settings(db, owner), body.expected_source_revision
            )
            preview = await preview_candidates(db, owner, body.request)
            selected = next(
                (c for c in preview.candidates if c.id == body.candidate_id), None
            )
            if not selected or not selected.can_add:
                raise HTTPException(409, "候选已变化、存在冲突或已忽略，请重新预览")
            for d in await store.rows(db, owner, "draft"):
                if (
                    d.data["status"] == "pending"
                    and d.data["source_revision"] == preview.source_revision
                    and d.data.get("source", {}).get("routine_candidate_id")
                    == selected.id
                ):
                    return store.view(d)
            return await imports.create_draft(
                db,
                owner,
                "calendar_event",
                {
                    "title": selected.title,
                    "starts_at": selected.starts_at.isoformat(),
                    "ends_at": selected.ends_at.isoformat(),
                },
                {
                    "routine_candidate_id": selected.id,
                    "explicit_rules": body.request.model_dump(mode="json"),
                    "candidate_basis": selected.basis,
                },
            )

        return await store.mutate(
            db, owner, "routine-draft", key, body.model_dump(mode="json"), op
        )

    @router.post("/daily-routine-dismiss")
    async def dismiss(
        body: CandidateDraft,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            store.revision(
                await store.settings(db, owner), body.expected_source_revision
            )
            preview = await preview_candidates(db, owner, body.request)
            if not any(c.id == body.candidate_id for c in preview.candidates):
                raise HTTPException(404, "候选不存在")
            rid = str(
                uuid5(NAMESPACE_URL, f"routine-dismissal:{owner}:{body.candidate_id}")
            )
            if not await db.get(Resource, rid):
                db.add(
                    Resource(
                        id=rid,
                        owner_id=owner,
                        kind="routine_dismissal",
                        data={
                            "candidate_id": body.candidate_id,
                            "source": "explicit_user_dismissal",
                            "rules": body.request.model_dump(mode="json"),
                        },
                    )
                )
                await db.flush()
            return {"dismissed": True, "candidate_id": body.candidate_id}

        return await store.mutate(
            db, owner, "routine-dismiss", key, body.model_dump(mode="json"), op
        )

    return router
