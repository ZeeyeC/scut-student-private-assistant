"""Repair existing arrangements using confirmed facts; no execution inference."""

from datetime import datetime

from fastapi import HTTPException
from pydantic import Field

from app import imports, store
from app.contracts import StrictModel

REPAIR_RULE = "preserve-valid-1"


class ReplanRemoval(StrictModel):
    id: str
    title: str
    reason: str


class ReplanAddition(StrictModel):
    id: str
    task_id: str
    step_id: str
    title: str
    starts_at: datetime
    ends_at: datetime


class ReplanReport(StrictModel):
    schema_version: int = 1
    rule_version: str = REPAIR_RULE
    source_revision: int
    timezone: str
    needs_changes: bool
    retained_ids: list[str]
    removed: list[ReplanRemoval]
    added: list[ReplanAddition]
    warnings: list[str]
    unallocated_minutes: int = Field(ge=0)
    execution_integration: str = "pending_person_b"


def replan_report(result):
    added = set(result["changes"]["added_ids"])
    return ReplanReport(
        source_revision=result["source_revision"],
        timezone=result["timezone"],
        needs_changes=bool(added or result["removed_blocks"]),
        retained_ids=result["changes"]["retained_ids"],
        removed=[
            {k: r[k] for k in ("id", "title", "reason")}
            for r in result["removed_blocks"]
        ],
        added=[
            {k: b[k] for k in ReplanAddition.model_fields}
            for b in result["blocks"]
            if b["id"] in added
        ],
        warnings=result["warnings"],
        unallocated_minutes=result["capacity"]["unallocated_minutes"],
    ).model_dump(mode="json")


async def replan_draft(db, owner, request):
    from app.planner import instant, planning_result

    if request.expected_source_revision is not None:
        store.revision(
            await store.settings(db, owner), request.expected_source_revision
        )
    inputs, result = await planning_result(
        db,
        owner,
        request.target_date,
        request.horizon_days,
        request.scope,
        repair=True,
        strategy=request.strategy,
    )
    report = replan_report(result)
    if not report["needs_changes"]:
        raise HTTPException(409, "没有需要替换或新增的安排；请先处理保留安排的警告")
    fingerprint = store.digest(
        {
            "revision": inputs["source_revision"],
            "target": inputs["target_date"],
            "days": inputs["horizon_days"],
            "scope": request.scope,
            "rule": REPAIR_RULE,
            "planner_rule": result["rule_version"],
            "strategy": request.strategy,
        }
    )
    for draft in await store.rows(db, owner, "draft"):
        if (
            draft.data["status"] != "pending"
            or draft.data.get("source", {}).get("replan_fingerprint") != fingerprint
        ):
            continue
        old = draft.data["payload"]
        old_ids = set(old["changes"]["added_ids"])
        removed_ids = set(old["changes"]["removed_ids"])
        clock = inputs["now_utc"]
        started = any(
            b["id"] in old_ids and instant(b["starts_at"]) < clock
            for b in old["blocks"]
        )
        started |= any(
            b["id"] in removed_ids and instant(b["starts_at"]) < clock
            for b in inputs["current_blocks"]
        )
        if not started and store.digest(old) == draft.data["source"].get(
            "generated_hash"
        ):
            return store.view(draft)
    payload = {
        **result,
        "scope": request.scope,
        "target_date": inputs["target_date"],
        "horizon_days": inputs["horizon_days"],
        "replanning": report,
    }
    return await imports.create_draft(
        db,
        owner,
        "plan",
        payload,
        {
            "planning_inputs": {**inputs, "now_utc": inputs["now_utc"].isoformat()},
            "generated_hash": store.digest(payload),
            "replan_fingerprint": fingerprint,
        },
    )
