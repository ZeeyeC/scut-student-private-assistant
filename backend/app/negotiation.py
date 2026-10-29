"""Persistent negotiation around A's planner, with no alternative allocator.

Services run in the caller's transaction. Mutating callers must wrap store.mutate
to replay historical receipts before checking today's revisions.
"""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import imports, store
from app.contracts import SchedulingConstraint
from app.db import Resource, now
from app.negotiation_contracts import (
    IntentAction,
    IntentChoose,
    IntentCreate,
    IntentPatch,
)


async def read_intents(db, owner):
    return [store.view(r) for r in await store.rows(db, owner, "planning_intent")]


async def validate_conditions(db, owner, conditions, source_revision):
    settings = await store.settings(db, owner)
    store.revision(settings, source_revision)
    if conditions.timezone != settings.data["timezone"]:
        raise HTTPException(409, "设置时区已变化，请读取设置后重新校对")
    limit = conditions.reduced_daily_limit_minutes
    if limit is not None and limit > settings.data["daily_limit_minutes"]:
        raise HTTPException(422, "临时负荷只能降低，不能放宽已确认每日上限")
    zone = ZoneInfo(conditions.timezone)
    end = conditions.target_date + timedelta(days=conditions.horizon_days)
    from app.planner import instant
    from app.planner import now as planning_now

    if conditions.target_date < planning_now().astimezone(zone).date():
        raise HTTPException(422, "请明确选择今天或未来的日期范围")
    for bid in conditions.keep_block_ids:
        b = await store.owned(db, owner, bid, "plan_block")
        day = instant(b.data["starts_at"]).astimezone(zone).date()
        if not conditions.target_date <= day < end:
            raise HTTPException(
                422, "保留项不在本轮范围内，请修改日期或选择范围内的安排"
            )


async def create_intent(db, owner, body: IntentCreate):
    await validate_conditions(db, owner, body.data, body.source_revision)
    r = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="planning_intent",
        data={
            "schema_version": 1,
            "status": "active",
            "source_revision": body.source_revision,
            "conditions": body.data.model_dump(mode="json"),
            "preview": None,
            "choice": None,
            "turns": [],
        },
    )
    db.add(r)
    await db.flush()
    return store.view(r)


async def invalidate_pending_choice(db, owner, r):
    choice = r.data.get("choice")
    if choice:
        draft = await store.owned(db, owner, choice["draft_id"], "draft")
        if draft.data["status"] == "pending":
            draft.data = {**draft.data, "status": "superseded"}
            draft.revision += 1


async def patch_intent(db, owner, rid, body: IntentPatch):
    r = await store.owned(db, owner, rid, "planning_intent")
    store.revision(r, body.revision)
    await validate_conditions(db, owner, body.data, body.source_revision)
    await invalidate_pending_choice(db, owner, r)
    turns = [
        *r.data["turns"],
        {
            "revision": r.revision,
            "conditions": r.data["conditions"],
            "recorded_at": now().isoformat(),
        },
    ]
    r.data = {
        **r.data,
        "status": "active",
        "source_revision": body.source_revision,
        "conditions": body.data.model_dump(mode="json"),
        "preview": None,
        "choice": None,
        "turns": turns,
    }
    r.revision += 1
    await db.flush()
    return store.view(r)


async def current_action(db, owner, rid, body):
    r = await store.owned(db, owner, rid, "planning_intent")
    store.revision(r, body.revision)
    store.revision(await store.settings(db, owner), body.source_revision)
    return r


async def preview_intent(db, owner, rid, body: IntentAction):
    from app.negotiation_contracts import IntentData
    from app.planner import build_plan, planning_result
    from app.planning_options import compare_plans, risk_report
    from app.replanning import replan_report

    r = await current_action(db, owner, rid, body)
    if r.data["status"] != "active":
        raise HTTPException(409, "请先继续修改本轮意图，再重新预览")
    conditions = IntentData.model_validate(r.data["conditions"])
    await validate_conditions(db, owner, conditions, body.source_revision)
    inputs, _ = await planning_result(
        db, owner, conditions.target_date, conditions.horizon_days
    )
    inputs = deepcopy(inputs)
    if conditions.reduced_daily_limit_minutes is not None:
        inputs["settings"]["daily_limit_minutes"] = (
            conditions.reduced_daily_limit_minutes
        )
    for strength, intervals in [
        ("hard", conditions.protected_intervals),
        ("soft", conditions.preferred_intervals),
    ]:
        for index, interval in enumerate(intervals):
            constraint = SchedulingConstraint(
                title="本轮临时保护" if strength == "hard" else "本轮临时偏好",
                timezone=conditions.timezone,
                strength=strength,
                **interval.model_dump(),
            )
            inputs["constraints"].append(
                {
                    "id": f"intent:{rid}:{strength}:{index}",
                    "kind": "scheduling_constraint",
                    "revision": r.revision,
                    "data": {
                        **constraint.model_dump(mode="json"),
                        "active": True,
                        "confirmed": True,
                        "source": "temporary_intent",
                    },
                }
            )
    protected_ids = set(conditions.keep_block_ids)
    for timer in await store.rows(db, owner, "execution_timer"):
        if timer.data["status"] not in ("finished", "discarded"):
            bid = timer.data["target"].get("plan_block_id")
            if bid:
                await store.owned(db, owner, bid, "plan_block")
                protected_ids.add(bid)
    preserved = {b["id"]: b for b in inputs["preserved_blocks"]}
    preserved.update(
        {b["id"]: b for b in inputs["current_blocks"] if b["id"] in protected_ids}
    )
    inputs["preserved_blocks"] = list(preserved.values())
    # A's selective repair commit replaces only calculated removed IDs. It must
    # not delete an unlocked block that this intent explicitly retained.
    inputs["repair"] = True
    options, conflicts, fingerprints = [], [], set()
    try:
        comparison = compare_plans(inputs)
        for option in comparison.options:
            candidate_inputs = {**deepcopy(inputs), "planning_strategy": option.id}
            result = build_plan(candidate_inputs)
            remaining = {b["id"]: b for b in result["blocks"]}
            lost = [
                bid
                for bid, block in preserved.items()
                if bid not in remaining or remaining[bid] != block
            ]
            # A reports conflicts rather than silently sacrificing locked facts.
            # Such a result is not advertised as a feasible alternative.
            if lost or result["warnings"]:
                conflicts.extend(
                    result["warnings"] or ["保留项与本轮条件冲突，请修改条件或保留选择"]
                )
                continue
            risks = risk_report(candidate_inputs, result).model_dump(mode="json")
            capacity = result["capacity"]
            if not result["blocks"] or (
                capacity["proposed_minutes"] == 0
                and (
                    capacity["unallocated_minutes"]
                    or capacity["unknown_estimate_count"]
                )
            ):
                conflicts.extend(
                    [x["reason"] for x in risks["risks"]]
                    or ["没有可安排的工作；请先添加或拆解任务"]
                )
                continue
            fingerprint = store.digest(
                sorted(
                    (b["task_id"], b["step_id"], b["starts_at"], b["ends_at"])
                    for b in result["blocks"]
                )
            )
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            payload = {
                **result,
                "scope": "range",
                "target_date": inputs["target_date"],
                "horizon_days": inputs["horizon_days"],
                "replanning": replan_report(result),
            }
            source = {
                "planning_inputs": {
                    **candidate_inputs,
                    "now_utc": inputs["now_utc"].isoformat(),
                },
                "generated_hash": store.digest(payload),
                "planning_intent_id": rid,
                "intent_revision": r.revision + 1,
            }
            options.append(
                {
                    **option.model_dump(mode="json"),
                    "risks": risks["risks"],
                    "changes": result["changes"],
                    "removed_blocks": result["removed_blocks"],
                    "payload": payload,
                    "source": source,
                }
            )
    except ValueError as exc:
        conflicts.append(str(exc))
    explanation = (
        "可比较两种不同安排；剩余负荷与风险请逐项校对"
        if len(options) > 1
        else "当前条件仅得到一种不同安排；甲方算法的相同结果已合并"
        if options
        else "当前条件没有可选择方案，请修改明确的条件或保留项；不会自行放宽硬约束"
    )
    preview = {
        "source_revision": body.source_revision,
        "options": options,
        "conflicts": list(dict.fromkeys(conflicts)),
        "explanation": explanation,
    }
    r.data = {**r.data, "source_revision": body.source_revision, "preview": preview}
    r.revision += 1
    await db.flush()
    return store.view(r)


async def choose_intent(db, owner, rid, body: IntentChoose):
    r = await current_action(db, owner, rid, body)
    preview = r.data.get("preview")
    if (
        r.data["status"] != "active"
        or not preview
        or preview["source_revision"] != body.source_revision
    ):
        raise HTTPException(409, "资料或意图已变化，请重新预览再选择")
    option = next((o for o in preview["options"] if o["id"] == body.option_id), None)
    if option is None:
        raise HTTPException(422, "该方案不在当前预览中")
    from app.planner import instant
    from app.planner import now as planning_now

    clock = planning_now()
    added = set(option["payload"]["changes"]["added_ids"])
    removed = set(option["payload"]["changes"]["removed_ids"])
    if any(
        b["id"] in added | removed and instant(b["starts_at"]) < clock
        for b in option["payload"]["blocks"]
        + option["source"]["planning_inputs"]["current_blocks"]
    ):
        raise HTTPException(409, "候选安排已开始，请重新预览")
    if store.digest(option["payload"]) != option["source"]["generated_hash"]:
        raise HTTPException(409, "候选内容已变化，请重新预览")
    draft = await imports.create_draft(
        db, owner, "plan", option["payload"], option["source"]
    )
    r.data = {
        **r.data,
        "status": "chosen",
        "choice": {"option_id": body.option_id, "draft_id": draft["id"]},
    }
    r.revision += 1
    await db.flush()
    return {"intent": store.view(r), "draft": draft}


async def cancel_intent(db, owner, rid, body: IntentAction):
    r = await current_action(db, owner, rid, body)
    await invalidate_pending_choice(db, owner, r)
    r.data = {**r.data, "status": "cancelled"}
    r.revision += 1
    await db.flush()
    return store.view(r)
