"""Recoverable clarification candidates delegating actual rules to A drafts."""

import re
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import ValidationError

from app import imports, store
from app.constraints import local_instant
from app.contracts import ConstraintDraft, SchedulingConstraint
from app.conversation_constraint_contracts import ConstraintIntentFields
from app.db import Resource, now

DAY = {c: n for n, c in enumerate("一二三四五六日", 1)} | {"天": 7}


def reference_day(stamp, zone):
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(zone).date()


def resolve_day(expression, reference, weekdays, recurrence):
    """Store only a canonical date, never the private trailing reason."""
    text = (expression or "").replace(" ", "")
    iso = re.search(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", text)
    if iso:
        return date.fromisoformat(iso.group()), recurrence, weekdays
    for word, offset in (("后天", 2), ("明天", 1), ("今天", 0)):
        if word in text:
            return reference + timedelta(days=offset), recurrence, weekdays
    match = re.search(r"周([一二三四五六日天])", text)
    if not match:
        return None, recurrence, weekdays
    weekday = DAY[match[1]]
    weekly = "每周" in text or recurrence == "weekly"
    offset = 2 if "下下周" in text else 1 if "下周" in text else 0
    monday = reference - timedelta(days=reference.weekday())
    target = monday + timedelta(weeks=offset, days=weekday - 1)
    if weekly and not offset and not any(word in text for word in ("这周", "本周")):
        target = reference + timedelta(days=(weekday - reference.isoweekday()) % 7)
    return (
        target,
        "weekly" if weekly else recurrence,
        sorted(set(weekdays or [weekday])) if weekly else [],
    )


def normalize(values, stamp, default_zone):
    body = ConstraintIntentFields.model_validate(values)
    zone_name = body.timezone or default_zone
    try:
        zone = ZoneInfo(zone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(422, "请输入有效IANA时区") from exc
    reference = reference_day(stamp, zone)
    try:
        day, recurrence, weekdays = resolve_day(
            body.day_expression, reference, body.weekdays, body.recurrence
        )
    except ValueError as exc:
        raise HTTPException(422, "日期无法识别，请明确年月日") from exc
    data = body.model_dump(mode="json")
    data.update(
        day_expression=day.isoformat() if day else None,
        timezone=zone_name,
        recurrence=recurrence,
        weekdays=weekdays,
    )
    return data, reference.isoformat()


def candidate(fields, reference):
    questions = []
    if not fields.get("day_expression"):
        questions.append("请明确哪一天，例如这周三、下周五或完整年月日。")
    if not fields.get("start_time") or not fields.get("end_time"):
        questions.append("请确认开始与结束钟点；下午、晚上不自动对应固定时段。")
    if fields.get("recurrence") == "weekly" and not fields.get("weekdays"):
        questions.append("每周重复需要明确适用星期。")
    if questions:
        return None, questions
    day = date.fromisoformat(fields["day_expression"])
    zone = ZoneInfo(fields["timezone"])
    a = datetime.combine(day, time.fromisoformat(fields["start_time"]))
    b = datetime.combine(
        day + timedelta(days=fields["end_day_offset"]),
        time.fromisoformat(fields["end_time"]),
    )
    if b <= a:
        return None, ["结束早于开始，请明确是否次日结束；不能自动跨午夜。"]
    if fields["recurrence"] == "once" and day < date.fromisoformat(reference):
        return None, ["所指日期已经过去，请确认日期；不会自动改成下周。"]
    try:
        value = SchedulingConstraint(
            title="不可安排",
            timezone=fields["timezone"],
            starts_at=local_instant(a, zone),
            ends_at=local_instant(b, zone),
            recurrence=fields["recurrence"],
            weekdays=fields["weekdays"],
            valid_until=fields["valid_until"],
            strength=fields["strength"],
        )
    except ValueError as exc:
        return None, [str(exc)]
    return ConstraintDraft(constraint=value).model_dump(mode="json"), []


async def view_intent(db, owner, row):
    data = dict(row.data)
    draft = None
    rule = None
    if data.get("draft_id"):
        linked = await db.get(Resource, data["draft_id"])
        if linked and linked.owner_id == owner and linked.kind == "draft":
            draft = await imports.review_view(db, owner, linked)
            if linked.data["status"] == "confirmed":
                ids = linked.data.get("summary", {}).get("saved_ids", [])
                if ids:
                    candidate_rule = await db.get(Resource, ids[0])
                    if (
                        candidate_rule
                        and candidate_rule.owner_id == owner
                        and candidate_rule.kind == "scheduling_constraint"
                    ):
                        rule = store.view(candidate_rule)
                        data["status"] = (
                            "confirmed" if candidate_rule.data["active"] else "disabled"
                        )
    return {**store.view(row), "data": data, "draft": draft, "constraint": rule}


async def read_intents(db, owner, thread_id=None):
    if thread_id:
        await store.owned(db, owner, thread_id, "agent_thread")
    return [
        await view_intent(db, owner, r)
        for r in await store.rows(db, owner, "constraint_intent")
        if thread_id is None or r.data.get("thread_id") == thread_id
    ]


async def create_intent(db, owner, body, *, reference_at=None):
    if body.thread_id:
        await store.owned(db, owner, body.thread_id, "agent_thread")
    cfg = await store.settings(db, owner)
    fields, reference = normalize(
        body.data.model_dump(), reference_at or now(), cfg.data["timezone"]
    )
    _, questions = candidate(fields, reference)
    row = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="constraint_intent",
        data={
            "schema_version": 1,
            "fields": fields,
            "reference_date": reference,
            "thread_id": body.thread_id,
            "status": "clarifying" if questions else "ready_for_review",
            "clarifications": questions,
            "draft_id": None,
            "prepared_draft_revision": None,
            "deactivation_requested": False,
        },
    )
    db.add(row)
    await db.flush()
    return await view_intent(db, owner, row)


async def patch_intent(db, owner, rid, body, *, reference_at=None):
    row = await store.owned(db, owner, rid, "constraint_intent")
    store.revision(row, body.revision)
    current = await view_intent(db, owner, row)
    if current["data"]["status"] in ("confirmed", "disabled", "cancelled"):
        raise HTTPException(409, "该意图已结束，请从规则列表发起修改")
    if not body.changes:
        raise HTTPException(422, "请提供要补充的字段")
    values = {**row.data["fields"], **body.changes}
    try:
        if "day_expression" in body.changes:
            fields, reference = normalize(
                values, reference_at or now(), row.data["fields"]["timezone"]
            )
        else:
            fields = ConstraintIntentFields.model_validate(values).model_dump(
                mode="json"
            )
            if not fields["timezone"]:
                fields["timezone"] = (await store.settings(db, owner)).data["timezone"]
            reference = row.data["reference_date"]
    except ValidationError as exc:
        raise HTTPException(
            422, "补充字段不合法，请核对日期、钟点、时区和重复规则"
        ) from exc
    payload, questions = candidate(fields, reference)
    data = {
        **row.data,
        "fields": fields,
        "reference_date": reference,
        "clarifications": questions,
        "status": "clarifying" if questions else "ready_for_review",
    }
    if data.get("draft_id"):
        linked = await store.owned(db, owner, data["draft_id"], "draft")
        store.revision(linked, data["prepared_draft_revision"])
        if linked.data["status"] != "pending":
            raise HTTPException(409, "草稿已失效，请重新核对")
        if payload:
            updated = await imports.edit_draft(
                db, owner, linked.id, linked.revision, payload
            )
            data["prepared_draft_revision"] = updated["revision"]
        else:
            linked.data = {**linked.data, "status": "cancelled"}
            linked.revision += 1
            data.update(draft_id=None, prepared_draft_revision=None)
    row.data = data
    row.revision += 1
    return await view_intent(db, owner, row)


async def prepare_intent(db, owner, rid, body):
    row = await store.owned(db, owner, rid, "constraint_intent")
    store.revision(row, body.revision)
    if row.data["status"] == "cancelled":
        raise HTTPException(409, "意图已取消")
    payload, questions = candidate(row.data["fields"], row.data["reference_date"])
    if questions:
        raise HTTPException(409, "；".join(questions))
    if row.data.get("draft_id"):
        linked = await store.owned(db, owner, row.data["draft_id"], "draft")
        if linked.data["status"] in ("pending", "confirmed"):
            return await view_intent(db, owner, row)
        raise HTTPException(409, "旧草稿已失效，请重新发起意图")
    draft = await imports.create_draft(
        db,
        owner,
        "scheduling_constraint",
        payload,
        {"constraint_intent_id": row.id, "privacy_reason_stored": False},
    )
    row.data = {
        **row.data,
        "draft_id": draft["id"],
        "prepared_draft_revision": draft["revision"],
    }
    row.revision += 1
    return await view_intent(db, owner, row)


async def cancel_intent(db, owner, rid, body):
    row = await store.owned(db, owner, rid, "constraint_intent")
    store.revision(row, body.revision)
    current = await view_intent(db, owner, row)
    if current.get("constraint"):
        # A confirmed rule needs a separate, explicit user state confirmation.
        row.data = {**row.data, "deactivation_requested": True}
    else:
        if row.data.get("draft_id"):
            linked = await store.owned(db, owner, row.data["draft_id"], "draft")
            if linked.data["status"] == "pending":
                linked.data = {**linked.data, "status": "cancelled"}
                linked.revision += 1
        row.data = {**row.data, "status": "cancelled"}
    row.revision += 1
    return await view_intent(db, owner, row)
