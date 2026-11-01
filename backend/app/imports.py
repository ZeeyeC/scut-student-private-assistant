from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import store
from app.campus_presets import effective_settings, preset_periods
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
        try:
            return Timetable.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, "课表无效：覆盖时至少保留一条课程，并核对周次和节次") from exc
    if kind == "assignment":
        try:
            data = AssignmentExtraction.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, "作业草稿格式无效") from exc
        if data.get("asset_ids"):
            if data.get("asset_id") is None:
                data["asset_id"] = data["asset_ids"][0]
            elif data["asset_id"] != data["asset_ids"][0]:
                raise HTTPException(422, "不可更换作业草稿关联的原图")
        elif data.get("asset_id"):
            data["asset_ids"] = [data["asset_id"]]
        if len(data.get("asset_ids", [])) == 1:
            only_asset = data["asset_ids"][0]
            for item in data["items"]:
                if item.get("source_asset_id") is None:
                    item["source_asset_id"] = only_asset
        return data
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
    if (
        kind in {"timetable", "timetable_recognition", "timetable_text"}
        and payload.get("campus_preset") is None
        and s.data.get("campus_preset")
    ):
        payload = {**payload, "campus_preset": s.data["campus_preset"]}
    source = dict(source or {})
    if kind == "assignment":
        image_ids = payload.get("asset_ids") or ([payload["asset_id"]] if payload.get("asset_id") else [])
        if len(image_ids) != len(set(image_ids)):
            raise HTTPException(422, "作业原图列表不能重复")
        for aid in image_ids:
            await store.owned(db, owner, aid, "asset")
        for candidate in payload["items"]:
            if candidate.get("source_asset_id") and candidate["source_asset_id"] not in image_ids:
                raise HTTPException(422, "作业条目的原图不在本次图片列表中")
        has_image = bool(payload.get("asset_id") or payload.get("asset_ids"))
        if not has_image:
            source.setdefault("reference_time", now().isoformat())
        else:
            source.setdefault(
                "asset_ids",
                list(
                    payload.get("asset_ids")
                    or ([payload["asset_id"]] if payload.get("asset_id") else [])
                ),
            )
            if source["asset_ids"] and not source.get("asset_id"):
                source["asset_id"] = source["asset_ids"][0]
            source.setdefault("deadline_followup", "pending")
        payload = suggest_assignment_deadlines(
            payload, s.data, source.get("reference_time")
        )
        if has_image:
            source["item_asset_ids"] = [
                item.get("source_asset_id") or payload.get("asset_id")
                for item in payload["items"]
            ]
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
        if (
            not reference
            and not draft.data["payload"].get("asset_id")
            and not draft.data["payload"].get("asset_ids")
        ):
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
    if r.data["draft_kind"] == "assignment":
        original_payload = r.data["payload"]
        original_asset = original_payload.get("asset_id")
        original_assets = original_payload.get("asset_ids") or (
            [original_asset] if original_asset else []
        )
        raw_payload = payload if isinstance(payload, dict) else {}
        if original_asset:
            if raw_payload.get("asset_id") not in (None, original_asset):
                raise HTTPException(422, "不可更换作业草稿关联的原图")
            validated["asset_id"] = original_asset
        if original_assets:
            if raw_payload.get("asset_ids") not in (None, [], original_assets):
                raise HTTPException(422, "不可更换作业草稿关联的原图")
            validated["asset_ids"] = list(original_assets)
        original_items = original_payload.get("items", [])
        source_map = r.data.get("source", {}).get("item_asset_ids") or [
            it.get("source_asset_id") or original_asset for it in original_items
        ]
        if original_assets or any(source_map):
            if len(validated["items"]) != len(original_items):
                raise HTTPException(422, "不可增删已绑定原图的作业条目")
            raw_items = raw_payload.get("items")
            for idx, item in enumerate(validated["items"]):
                expected_source = (
                    source_map[idx]
                    if idx < len(source_map) and source_map[idx]
                    else original_items[idx].get("source_asset_id") or original_asset
                )
                raw_item = (
                    raw_items[idx]
                    if isinstance(raw_items, list)
                    and idx < len(raw_items)
                    and isinstance(raw_items[idx], dict)
                    else {}
                )
                supplied_source = raw_item.get("source_asset_id")
                if supplied_source is not None and supplied_source != expected_source:
                    raise HTTPException(422, "不可更换作业条目关联的原图")
                item["source_asset_id"] = expected_source
                original_evidence = original_items[idx].get("evidence", [])
                if "evidence" in raw_item and raw_item["evidence"] != original_evidence:
                    raise HTTPException(422, "不可更换作业截图的原文证据")
                item["evidence"] = list(original_evidence)
        for aid in {
            *(validated.get("asset_ids") or []),
            *([validated["asset_id"]] if validated.get("asset_id") else []),
            *(
                item.get("source_asset_id")
                for item in validated["items"]
                if item.get("source_asset_id")
            ),
        }:
            await store.owned(db, owner, aid, "asset")
        for item in validated["items"]:
            if item.get("course_id"):
                await store.owned(db, owner, item["course_id"], "course")
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
    # A fresh timetable conflict token guards the current complete source set.
    # Legacy clients without it retain the original settings revision guard;
    # decompositions validate the actual task version in save_steps below.
    if (d.data["draft_kind"] in {
        "plan",
        "timetable",
        "course_change",
        "semester_calendar",
    } or d.data.get("source", {}).get("routine_candidate_id")) and not (
        d.data["draft_kind"] == "timetable" and conflict_token is not None
    ):
        store.revision(s, d.data["source_revision"])
    payload = validate_payload(d.data["draft_kind"], d.data["payload"])
    effective = (
        effective_settings(s.data, payload)
        if d.data["draft_kind"]
        in {"timetable", "timetable_recognition", "timetable_text"}
        else s.data
    )
    if d.data["draft_kind"] == "timetable" and payload["save_mode"] == "replace" and conflict_token is None:
        raise HTTPException(422, "覆盖课表前请重新检查冲突并确认替换范围")
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
    removed_course_ids = []
    if d.data["draft_kind"] == "semester_calendar":
        from app.semester_calendar import save_semester

        ids = await save_semester(db, owner, d, payload)
    if d.data["draft_kind"] == "course_change":
        from app.course_changes import save_change

        ids = await save_change(db, owner, d, payload)
    if d.data["draft_kind"] in {"timetable_recognition", "timetable_text"}:
        from app.timetable_recognition import save_recognized_courses

        ids = await save_recognized_courses(db, owner, d, payload, effective)
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
        for aid in {
            *(payload.get("asset_ids") or []),
            *([payload["asset_id"]] if payload.get("asset_id") else []),
            *(
                c.get("source_asset_id")
                for c in payload["items"]
                if c.get("source_asset_id")
            ),
        }:
            await store.owned(db, owner, aid, "asset")
        for candidate in payload["items"]:
            validate_deadline_basis(candidate, s.data)
            if candidate.get("course_id"):
                await store.owned(db, owner, candidate["course_id"], "course")
            item_asset_id = candidate.get("source_asset_id") or payload.get("asset_id")
            r = Resource(
                id=str(uuid4()),
                owner_id=owner,
                kind="task",
                data={
                    **candidate,
                    "status": "open",
                    "asset_id": item_asset_id,
                    "source_asset_id": item_asset_id,
                    "remedy_due_at": None,
                },
            )
            db.add(r)
            ids.append(r.id)
    if d.data["draft_kind"] == "timetable":
        if payload.get("campus_preset"):
            for course in payload["courses"]:
                if any(
                    p not in effective["periods"] and str(p) not in effective["periods"]
                    for p in course["periods"]
                ):
                    raise HTTPException(422, "课程节次超出所选校区模板范围，请在设置中自定义节次")
        old = {r.data["source_key"]: r for r in await store.rows(db, owner, "course")}
        for course in payload["courses"]:
            if max(course["weeks"]) > effective["week_count"]:
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
        removed_courses = []
        # Explicit reviewed replacement is separate from claiming full capture.
        if payload["save_mode"] == "replace" or (payload["completeness"] == "full" and d.data.get("source", {}).get(
            "verified_full"
        )):
            for k, r in old.items():
                if k not in {c["source_key"] for c in payload["courses"]}:
                    removed_course_ids.append(r.id)
                    removed_courses.append(r)
                    await db.delete(r)
        if removed_courses:
            from app.timetable_replacement import retire_course_links

            await retire_course_links(db, owner, removed_courses, d.id)
    if (
        d.data["draft_kind"] in {"timetable", "timetable_recognition", "timetable_text"}
        and payload.get("campus_preset")
    ):
        s.data = {
            **s.data,
            "campus_preset": payload["campus_preset"],
            "periods": preset_periods(payload["campus_preset"]),
        }
    await store.bump(db, owner)
    summary = {"draft_id": d.id, "saved_ids": ids}
    if d.data["draft_kind"] == "timetable":
        summary["removed_course_ids"] = removed_course_ids
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
