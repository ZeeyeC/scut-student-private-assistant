"""Consume the existing fact events into one recoverable, review-only notice."""

from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field

from app import store
from app.contracts import ResourceView, StrictModel
from app.db import Resource
from app.planning_history import record_change

FACT_KINDS = (
    "settings",
    "task",
    "step",
    "course",
    "exception",
    "fixed_event",
    "scheduling_constraint",
    "execution",
    "execution_timer",
    "user_profile",
    "goal",
)
EVENT_TYPES = {
    "execution_changed",
    "execution_timer_changed",
    "profile_changed",
    "goal_changed",
    "constraint_changed",
    "course_exception_changed",
    "duration_suggestion_action",
    "planning_sources_changed",
}


def notice_id(owner):
    return str(uuid5(NAMESPACE_URL, f"replan-notice:{owner}"))


class ConsumeRequest(StrictModel):
    app_active: bool = True


class NoticeAction(StrictModel):
    revision: int = Field(ge=1)
    source_revision: int = Field(ge=1)


class ChangeResult(StrictModel):
    consumed: int
    notice: ResourceView | None


async def read_notice(db, owner):
    row = await db.get(Resource, notice_id(owner))
    if not row or row.owner_id != owner or row.kind != "replan_notice":
        return None
    result = store.view(row)
    # Derived status; GET never updates facts, the draft or the consumer cursor.
    settings = await store.rows(db, owner, "settings")
    data = dict(result["data"])
    if data.get("draft_id"):
        draft = await db.get(Resource, data["draft_id"])
        if draft and draft.owner_id == owner:
            if draft.data["status"] == "confirmed":
                data["state"] = "confirmed"
            elif draft.data["status"] != "pending":
                data["state"] = "invalidated"
    if (
        data["state"] not in ("confirmed", "resolved")
        and settings
        and settings[0].revision != data["source_revision"]
    ):
        data["state"] = "invalidated"
    return {**result, "data": data}


async def consume_changes(db, owner, app_active=True):
    if not app_active:
        return {"consumed": 0, "notice": await read_notice(db, owner)}
    settings = await store.settings(db, owner)
    from app.planner import now

    manifest = [
        (
            "planning_day",
            now().astimezone(ZoneInfo(settings.data["timezone"])).date().isoformat(),
        )
    ]
    for kind in FACT_KINDS:
        for row in await store.rows(db, owner, kind):
            # Timer heartbeats are not fresh planning facts. Start/pause/end are events.
            if kind == "execution_timer":
                value = store.digest(
                    {"status": row.data["status"], "target": row.data["target"]}
                )
            elif kind == "settings":
                value = store.digest(row.data)
            else:
                value = row.revision
            manifest.append((kind, row.id, value))
    signature = store.digest(manifest)
    row = await db.get(Resource, notice_id(owner))
    events = [
        e
        for e in await store.rows(db, owner, "planning_event")
        if e.data["event_type"] in EVENT_TYPES and not e.data.get("planning_consumed")
    ]
    if row and row.data["manifest_hash"] == signature and not events:
        return {"consumed": 0, "notice": await read_notice(db, owner)}
    settings = await store.settings(db, owner)
    if not row or row.data["manifest_hash"] != signature:
        event_id = await record_change(
            db,
            owner,
            "planning_sources_changed",
            settings.id,
            settings.revision,
            {"manifest_hash": signature, "kinds": list(FACT_KINDS)},
        )
        event = await db.get(Resource, event_id)
        if event not in events and not event.data.get("planning_consumed"):
            events.append(event)
    from app.planner import planning_result
    from app.replanning import replan_report

    _, result = await planning_result(db, owner, repair=True)
    report = replan_report(result)
    semantic = store.digest(
        {
            "slots": sorted(
                (b["step_id"], b["starts_at"], b["ends_at"]) for b in result["blocks"]
            ),
            "removed": sorted((r["id"], r["reason"]) for r in report["removed"]),
            "warnings": report["warnings"],
            "unscheduled": result["unscheduled"],
        }
    )
    unchanged = row and row.data["fingerprint"] == semantic
    state = (
        (
            row.data["state"]
            if unchanged and row.data["state"] == "dismissed"
            else "pending"
        )
        if report["needs_changes"] or report["warnings"]
        else "resolved"
    )
    data = {
        "schema_version": 1,
        "manifest_hash": signature,
        "fingerprint": semantic,
        "source_revision": settings.revision,
        "state": state,
        "report": report,
        "event_ids": [e.id for e in events],
        "draft_id": row.data.get("draft_id")
        if unchanged and row.data["source_revision"] == settings.revision
        else None,
    }
    if row:
        row.data = data
        row.revision += 1
    else:
        row = Resource(
            id=notice_id(owner), owner_id=owner, kind="replan_notice", data=data
        )
        db.add(row)
    for event in events:
        event.data = {
            **event.data,
            "planning_consumed": True,
            "planning_notice_id": row.id,
        }
        event.revision += 1
    await db.flush()
    return {"consumed": len(events), "notice": await read_notice(db, owner)}


def changes_router(get_db, current_user):
    router = APIRouter(prefix="/api/replanning/changes")

    @router.get("", response_model=ResourceView | None)
    async def read(user=Depends(current_user), db=Depends(get_db)):
        return await read_notice(db, str(user.id))

    @router.post("", response_model=ChangeResult)
    async def consume(
        body: ConsumeRequest, user=Depends(current_user), db=Depends(get_db)
    ):
        return await consume_changes(db, str(user.id), body.app_active)

    @router.post("/dismiss", response_model=ResourceView)
    async def dismiss(
        body: NoticeAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def operation():
            row = await store.owned(db, owner, notice_id(owner), "replan_notice")
            store.revision(row, body.revision)
            store.revision(await store.settings(db, owner), body.source_revision)
            if row.data["source_revision"] != body.source_revision:
                raise HTTPException(409, "变化建议已失效，请重新检查")
            row.data = {**row.data, "state": "dismissed"}
            row.revision += 1
            return store.view(row)

        return await store.mutate(
            db, owner, "replan-notice-dismiss", key, body.model_dump(), operation
        )

    @router.post("/draft", response_model=ResourceView)
    async def draft(
        body: NoticeAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def operation():
            row = await store.owned(db, owner, notice_id(owner), "replan_notice")
            store.revision(row, body.revision)
            store.revision(await store.settings(db, owner), body.source_revision)
            if (
                row.data["source_revision"] != body.source_revision
                or row.data["state"] != "pending"
            ):
                raise HTTPException(409, "变化建议已失效，请重新检查")
            from app.planner import PlanRequest
            from app.replanning import replan_draft

            result = await replan_draft(
                db, owner, PlanRequest(expected_source_revision=body.source_revision)
            )
            row.data = {**row.data, "draft_id": result["id"]}
            row.revision += 1
            return result

        return await store.mutate(
            db, owner, "replan-notice-draft", key, body.model_dump(), operation
        )

    return router
