from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import store
from app.contracts import (
    AssignmentExtraction,
    ConstraintDraft,
    Decomposition,
    FixedEvent,
    Timetable,
)
from app.db import Resource, now
from app.deadlines import suggest_assignment_deadlines, validate_deadline_basis
from app.timetable_contracts import TimetableRecognition


def validate_payload(kind, payload):
    if kind == "semester_calendar":
        from app.semester_calendar import validate_semester_payload

        return validate_semester_payload(payload)
    if kind == "course_change":
        from app.course_changes import CourseChange

        try:
            return CourseChange.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, "课程调整草稿无效，请重新选择课程与时间") from exc
    if kind in {"timetable_recognition", "timetable_text"}:
        try:
            return TimetableRecognition.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, "课表识别草稿格式无效，请核对字段") from exc
    if kind == "scheduling_constraint":
        try:
            return ConstraintDraft.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(
                422, "禁排草稿无效，请核对时间、时区和修改版本"
            ) from exc
    if kind == "calendar_event":
        return FixedEvent.model_validate(payload).model_dump(mode="json")
    if kind == "timetable":
        return Timetable.model_validate(payload).model_dump(mode="json")
    if kind == "assignment":
        return AssignmentExtraction.model_validate(payload).model_dump(mode="json")
    if kind == "decomposition":
        return Decomposition.model_validate(payload).model_dump(mode="json")
    if kind == "plan":
        if not isinstance(payload.get("blocks"), list) or not isinstance(
            payload.get("unscheduled"), list
        ):
            raise HTTPException(422, "计划结构无效")
        return payload
    raise HTTPException(422, "未知草稿类型")


async def create_draft(db, owner, kind, payload, source=None):
    payload = validate_payload(kind, payload)
    s = await store.settings(db, owner)
    source = dict(source or {})
    if kind == "assignment":
        if not payload.get("asset_id"):
            source.setdefault("reference_time", now().isoformat())
        payload = suggest_assignment_deadlines(
            payload, s.data, source.get("reference_time")
        )
    if kind == "plan":
        for previous in await store.rows(db, owner, "draft"):
            if (
                previous.data["draft_kind"] == "plan"
                and previous.data["status"] == "pending"
            ):
                previous.data = {**previous.data, "status": "superseded"}
                previous.revision += 1
    data = {
        "draft_kind": kind,
        "payload": payload,
        "source_revision": s.revision,
        "source": source,
        "status": "pending",
        "summary": None,
    }
    if kind == "timetable":
        old = {r.data["source_key"]: r for r in await store.rows(db, owner, "course")}
        new = {c["source_key"]: c for c in payload["courses"]}
        data["changes"] = {
            "added": [k for k in new if k not in old],
            "changed": [k for k in new if k in old and new[k] != old[k].data],
            "possibly_removed": [k for k in old if k not in new],
        }
    r = Resource(id=str(uuid4()), owner_id=owner, kind="draft", data=data)
    db.add(r)
    await db.flush()
    return store.view(r)


async def review_view(db, owner, draft):
    if draft.data["draft_kind"] == "timetable_text":
        from app.timetable_text import view

        return await view(db, owner, draft)
    result = store.view(draft)
    if draft.data["draft_kind"] == "assignment" and draft.data["status"] == "pending":
        s = await store.settings(db, owner)
        reference = draft.data.get("source", {}).get("reference_time")
        if not reference and not draft.data["payload"].get("asset_id"):
            reference = draft.created_at
        proposed = suggest_assignment_deadlines(
            draft.data["payload"], s.data, reference
        )
        if proposed != draft.data["payload"]:
            # Read-only proposal for drafts created before week resolution existed.
            result["data"] = {**draft.data, "suggested_payload": proposed}
    return result


async def edit_draft(db, owner, rid, expected, payload):
    r = await store.owned(db, owner, rid, "draft")
    store.revision(r, expected)
    if r.data["status"] != "pending":
        raise HTTPException(409, "草稿已确认或失效")
    if r.data["draft_kind"] in {"course_change", "semester_calendar"}:
        raise HTTPException(422, "课程调整与预览绑定，请删除后重新生成草稿")
    validated = validate_payload(r.data["draft_kind"], payload)
    if r.data["draft_kind"] in {"timetable_recognition", "timetable_text"}:
        from app.timetable_recognition import validate_review_edit

        validate_review_edit(r.data["payload"], validated)
    if r.data["draft_kind"] == "scheduling_constraint":
        # Editing content must not retarget an already-reviewed amendment.
        if any(
            validated[k] != r.data["payload"][k]
            for k in ("constraint_id", "constraint_revision")
        ):
            raise HTTPException(422, "请从禁排列表重新发起修改，不可更换草稿目标或版本")
    r.data = {**r.data, "payload": validated}
    r.revision += 1
    return store.view(r)


async def commit_draft(db, owner, draft_id, expected, conflict_token=None):
    d = await store.owned(db, owner, draft_id, "draft")
    if d.data["status"] == "confirmed":
        return d.data["summary"]
    if d.data["status"] != "pending":
        raise HTTPException(409, "草稿已取消或失效")
    browser_session = d.data.get("source", {}).get("browser_session")
    if browser_session:
        from app.browser_imports import get_import

        b = await get_import(db, owner, browser_session)
        if b.data["status"] != "preview_ready":
            raise HTTPException(409, "导入已取消或过期，请重新导入")
    store.revision(d, expected)
    s = await store.settings(db, owner)
    # New independent facts do not depend on every unrelated database change.
    # Plans/timetable replacements retain their full source version guard;
    # decompositions validate the actual task version in save_steps below.
    if d.data["draft_kind"] in {
        "plan",
        "timetable",
        "course_change",
        "semester_calendar",
    } or d.data.get("source", {}).get("routine_candidate_id"):
        store.revision(s, d.data["source_revision"])
    payload = validate_payload(d.data["draft_kind"], d.data["payload"])
    from app.conflicts import REVIEW_KINDS, draft_conflicts

    conflict_report = None
    if d.data["draft_kind"] in REVIEW_KINDS:
        conflict_report = await draft_conflicts(db, owner, d, payload)
        if (
            conflict_token is not None
            and conflict_token != conflict_report["conflict_token"]
        ):
            raise HTTPException(
                409, "课程、固定事项或转移设置已变化，请重新检查冲突后保存"
            )
    ids = []
    if d.data["draft_kind"] == "semester_calendar":
        from app.semester_calendar import save_semester

        ids = await save_semester(db, owner, d, payload)
    if d.data["draft_kind"] == "course_change":
        from app.course_changes import save_change

        ids = await save_change(db, owner, d, payload)
    if d.data["draft_kind"] in {"timetable_recognition", "timetable_text"}:
        from app.timetable_recognition import save_recognized_courses

        ids = await save_recognized_courses(db, owner, d, payload, s.data)
    if d.data["draft_kind"] == "scheduling_constraint":
        from app.constraints import save_constraint

        ids = await save_constraint(db, owner, d, payload)
    if d.data["draft_kind"] == "calendar_event":
        r = Resource(id=str(uuid4()), owner_id=owner, kind="fixed_event", data=payload)
        db.add(r)
        ids.append(r.id)
    if d.data["draft_kind"] == "plan":
        from app.planner import save_plan

        ids = await save_plan(db, owner, d, payload)
    if d.data["draft_kind"] == "decomposition":
        from app.tasks import save_steps

        ids = await save_steps(db, owner, payload)
    if d.data["draft_kind"] == "assignment":
        if payload.get("asset_id"):
            await store.owned(db, owner, payload["asset_id"], "asset")
        for candidate in payload["items"]:
            validate_deadline_basis(candidate, s.data)
            if candidate.get("course_id"):
                await store.owned(db, owner, candidate["course_id"], "course")
            r = Resource(
                id=str(uuid4()),
                owner_id=owner,
                kind="task",
                data={
                    **candidate,
                    "status": "open",
                    "asset_id": payload.get("asset_id"),
                    "remedy_due_at": None,
                },
            )
            db.add(r)
            ids.append(r.id)
    if d.data["draft_kind"] == "timetable":
        old = {r.data["source_key"]: r for r in await store.rows(db, owner, "course")}
        for course in payload["courses"]:
            if max(course["weeks"]) > s.data["week_count"]:
                raise HTTPException(422, "周次超过学期范围")
            r = old.get(course["source_key"])
            if r:
                r.data = course
                r.revision += 1
            else:
                r = Resource(
                    id=str(uuid4()), owner_id=owner, kind="course", data=course
                )
                db.add(r)
            ids.append(r.id)
        # Full deletion is permitted only for a verified capture source.
        if payload["completeness"] == "full" and d.data.get("source", {}).get(
            "verified_full"
        ):
            for k, r in old.items():
                if k not in {c["source_key"] for c in payload["courses"]}:
                    await db.delete(r)
    await store.bump(db, owner)
    summary = {"draft_id": d.id, "saved_ids": ids}
    if conflict_report is not None:
        summary.update(
            conflict_report=conflict_report,
            conflict_reviewed=conflict_token is not None,
        )
    d.data = {**d.data, "status": "confirmed", "summary": summary}
    d.revision += 1
    if d.data.get("source", {}).get("browser_session"):
        b = await store.owned(
            db, owner, d.data["source"]["browser_session"], "browser_import"
        )
        b.data = {**b.data, "status": "completed"}
        b.revision += 1
    await db.flush()
    return summary
