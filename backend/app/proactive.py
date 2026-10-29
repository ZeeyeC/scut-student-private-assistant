"""B-owned notification lifecycle. A remains the sole scheduling calculator.

The caller supplies one serialized transaction. No timers, models, OS alerts,
external-app observations, or formal plan writes occur here.
"""

from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import store
from app.db import Resource, now
from app.planning_history import record_change
from app.proactive_contracts import ProactivePreferences

ACTIVE = {"pending", "snoozed", "dismissed", "accepted"}
GAPS = [
    "实际投入未知时保持未知；甲当前耗时计算不等于权威执行汇总",
    "容量是时间上限，不保证工作可完成；缺少真实准备/通勤依据时不推断提前量",
]


def preferences_id(owner):
    return str(uuid5(NAMESPACE_URL, f"proactive-preferences:{owner}"))


async def read_preferences(db, owner):
    resource = await db.get(Resource, preferences_id(owner))
    if resource and (
        resource.owner_id != owner or resource.kind != "proactive_preferences"
    ):
        raise HTTPException(404, "设置不存在")
    return {
        "id": resource.id if resource else None,
        "kind": "proactive_preferences",
        "revision": resource.revision if resource else 0,
        "contract_version": "proactive-v1",
        "data": resource.data
        if resource
        else ProactivePreferences().model_dump(mode="json"),
    }


async def write_preferences(db, owner, body):
    current = await read_preferences(db, owner)
    if current["revision"] != body.revision:
        raise HTTPException(409, "建议设置已更新，请刷新后重新校对")
    resource = await db.get(Resource, preferences_id(owner))
    if resource:
        resource.data = body.data.model_dump(mode="json")
        resource.revision += 1
    else:
        resource = Resource(
            id=preferences_id(owner),
            owner_id=owner,
            kind="proactive_preferences",
            data=body.data.model_dump(mode="json"),
        )
        db.add(resource)
    await db.flush()
    await record_change(
        db,
        owner,
        "proactive_preferences_changed",
        resource.id,
        resource.revision,
        {"contract_version": "proactive-v1"},
    )
    return await read_preferences(db, owner)


def quiet_at(preferences, clock):
    """Half-open local wall-clock windows; weekdays identify the starting day.

    Overnight Sunday 22:00–02:00 includes Monday 01:00. ZoneInfo converts
    instants first, so both folds of a DST repeated hour are quiet.
    """
    if not preferences.get("timezone") or not preferences.get("quiet_hours"):
        return False
    local = clock.astimezone(ZoneInfo(preferences["timezone"]))
    weekday, previous = local.isoweekday(), (local.isoweekday() - 2) % 7 + 1
    clock_text = local.strftime("%H:%M")
    for window in preferences["quiet_hours"]:
        start, end = window["start"], window["end"]
        if start < end:
            if weekday in window["weekdays"] and start <= clock_text < end:
                return True
        elif (weekday in window["weekdays"] and clock_text >= start) or (
            previous in window["weekdays"] and clock_text < end
        ):
            return True
    return False


def suppression(preferences):
    if not preferences["enabled"]:
        return "disabled"
    if quiet_at(preferences, now()):
        return "quiet_hours"
    return None


def suggestion_view(resource, preferences, suppressed=None):
    data = dict(resource.data)
    data["visible"] = (
        not (suppressed or suppression(preferences))
        and preferences["categories"][data["category"]]
        and data["state"] == "pending"
    )
    return {
        "id": resource.id,
        "kind": resource.kind,
        "revision": resource.revision,
        "data": data,
    }


async def list_suggestions(
    db, owner, *, suppressed=None, capacity=None, source_revision=None
):
    preference = await read_preferences(db, owner)
    suppressed = suppressed or suppression(preference["data"])
    resources = await store.rows(db, owner, "proactive_suggestion")

    def order(resource):
        evidence = resource.data["evidence"]
        risk = evidence.get("risk", {})
        due = evidence.get("due_at")
        return (
            resource.data["rank"],
            datetime.fromisoformat(due).timestamp() if due else float("inf"),
            0 if "依赖未满足" in risk.get("reason", "") else 1,
            -(risk.get("remaining_minutes") or 0),
            -evidence.get("priority", 0),
            resource.data["first_seen_at"],
            resource.id,
        )

    resources.sort(key=order)
    return {
        "contract_version": "proactive-v1",
        "preferences": preference,
        "suggestions": [
            suggestion_view(r, preference["data"], suppressed) for r in resources
        ],
        "suppression": suppressed,
        "source_revision": source_revision,
        "capacity": capacity,
    }


def candidates(inputs, result):
    """Translate A's reports into explainable issues, never recalculate a plan."""
    from app.planner import instant
    from app.planning_options import risk_report
    from app.replanning import replan_report

    risks = risk_report(inputs, result).model_dump(mode="json")
    capacity = result["capacity"]
    repair = replan_report(result)
    tasks = {t["id"]: t for t in inputs["tasks"]}
    steps = {s["id"]: s for s in inputs["steps"]}
    found = []

    def source_refs(task_id=None, step_id=None):
        return [
            {"id": r["id"], "kind": r["kind"], "revision": r["revision"]}
            for r in (tasks.get(task_id), steps.get(step_id))
            if r
        ]

    def work_basis(task_id, step_id=None):
        task = tasks.get(task_id, {}).get("data", {})
        step = steps.get(step_id, {}).get("data", {})
        return {
            "task": {
                k: task.get(k)
                for k in ("title", "status", "priority", "due_at", "remedy_due_at")
            },
            "step": {
                k: step.get(k)
                for k in (
                    "title",
                    "status",
                    "estimated_minutes",
                    "spent_minutes",
                    "dependency_ids",
                )
            },
        }

    def add(
        category,
        issue,
        title,
        reasons,
        rank,
        evidence,
        proof,
        task_id=None,
        step_id=None,
    ):
        found.append(
            {
                "category": category,
                "issue_key": issue,
                "fingerprint": store.digest(
                    {"category": category, "issue": issue, "result": proof}
                ),
                "title": title,
                "reasons": reasons,
                "gaps": list(GAPS),
                "rank": rank,
                "source_revision": inputs["source_revision"],
                "sources": source_refs(task_id, step_id),
                "evidence": evidence,
                "task_id": task_id,
            }
        )

    for risk in risks["risks"]:
        tid, sid = risk["task_id"], risk["step_id"]
        task = tasks.get(tid, {}).get("data", {})
        due = task.get("remedy_due_at") or task.get("due_at")
        category = (
            "unknown_estimate" if risk["code"] == "unknown_estimate" else "deadline"
        )
        rank = (
            0
            if risk["code"] == "overdue"
            else 20
            if category == "unknown_estimate"
            else 10
        )
        # Deterministic risk order: overdue, confirmed deadline, then dependency
        # or estimate gaps; tie-break using remaining work and explicit priority.
        proof = {"risk": risk, "work": work_basis(tid, sid)}
        add(
            category,
            f"risk:{tid}:{sid}",
            f"{'预计耗时待补充' if category == 'unknown_estimate' else '截止与未排风险'}：{risk['title']}",
            [
                risk["reason"],
                f"已确认截止：{due}" if due else "截止时间未知",
                f"甲计算未排工作量：{risk['remaining_minutes']} 分钟"
                if risk["remaining_minutes"] is not None
                else "预计耗时未知，不能按0分钟处理",
            ],
            rank,
            {
                "risk": risk,
                "due_at": due,
                "priority": task.get("priority", 2),
                "dependency_ids": steps.get(sid, {})
                .get("data", {})
                .get("dependency_ids", []),
            },
            proof,
            tid,
            sid,
        )

    # A may fit all work while a confirmed deadline still deserves an in-app
    # reminder. Read only the confirmed instant; do not estimate preparation.
    risk_tasks = {
        risk["task_id"] for risk in risks["risks"] if risk["code"] != "unknown_estimate"
    }
    clock = instant(inputs["now_utc"])
    for tid, resource in tasks.items():
        task = resource["data"]
        due = task.get("remedy_due_at") or task.get("due_at")
        if task.get("status") != "open" or not due or tid in risk_tasks:
            continue
        remaining = (instant(due) - clock).total_seconds()
        if not 0 <= remaining <= 48 * 3600:
            continue
        add(
            "deadline",
            f"upcoming:{tid}",
            f"已确认截止临近：{task['title']}",
            [f"已确认截止：{due}", "截止在48小时内；现有容量可排入不代表已经完成"],
            10,
            {
                "due_at": due,
                "priority": task.get("priority", 2),
                "trigger": "confirmed_deadline_within_48h",
            },
            {"work": work_basis(tid), "trigger": "confirmed_deadline_within_48h"},
            tid,
        )

    if capacity["unallocated_minutes"] > 0:
        add(
            "capacity",
            "capacity:range",
            "部分工作未能排入可用时间",
            [
                f"甲计算所需 {capacity['required_minutes']} 分钟；共享容量上限 {capacity['capacity_upper_bound_minutes']} 分钟",
                f"至少 {capacity['unallocated_minutes']} 分钟未排入；截止、依赖与碎片均可能限制安排",
            ],
            15,
            {"capacity": capacity},
            {
                "required_minutes": capacity["required_minutes"],
                "capacity_upper_bound_minutes": capacity[
                    "capacity_upper_bound_minutes"
                ],
                "unallocated_minutes": capacity["unallocated_minutes"],
                "unscheduled": capacity["unscheduled"],
            },
        )

    # A has already checked dependency order, deadlines, hard protections and
    # budget for these proposed blocks. Require an actual >=20 minute interval
    # AND proposed open work inside it; a free window alone is insufficient.
    added_ids = set(result["changes"]["added_ids"])
    clock = instant(inputs["now_utc"])
    available = []
    for day in capacity["days"]:
        if day["date"] != inputs["target_date"] or day["budget_remaining_minutes"] < 20:
            continue
        for window in day["free_windows"]:
            a, b = instant(window["starts_at"]), instant(window["ends_at"])
            if (b - max(a, clock)).total_seconds() < 1200:
                continue
            for block in result["blocks"]:
                tid, sid = block["task_id"], block["step_id"]
                if (
                    block["id"] not in added_ids
                    or tasks.get(tid, {}).get("data", {}).get("status") != "open"
                    or steps.get(sid, {}).get("data", {}).get("status") != "open"
                ):
                    continue
                c, d = instant(block["starts_at"]), instant(block["ends_at"])
                if a <= c < d <= b and (d - c).total_seconds() >= 1200:
                    available.append((c, window, block))
    if available:
        _, window, block = min(available, key=lambda r: r[0])
        tid, sid = block["task_id"], block["step_id"]
        # A's generated IDs include global revision. Exclude them and the moving
        # current-minute start so unrelated edits/clock ticks cannot re-alert.
        add(
            "available_window",
            f"window:{tid}:{sid}:{window['ends_at']}",
            "有依据的20分钟学习空档",
            [
                f"甲核对空档 {window['starts_at']} 至 {window['ends_at']}",
                f"存在已校验的待完成步骤：{block['title']}；采纳后仍需校对安排",
            ],
            30,
            {
                "free_window": window,
                "proposed_work": {
                    k: block[k]
                    for k in ("task_id", "step_id", "title", "starts_at", "ends_at")
                },
            },
            {"window_ends_at": window["ends_at"], "work": work_basis(tid, sid)},
            tid,
            sid,
        )

    block_warnings = [
        warning
        for warning in repair["warnings"]
        if any(
            warning.startswith(block.get("title", "旧安排") + "：")
            for block in inputs["current_blocks"]
        )
    ]
    if repair["removed"] or block_warnings:
        removed_ids = {r["id"] for r in repair["removed"]}
        affected = [
            b
            for b in inputs["current_blocks"]
            if b["id"] in removed_ids
            or any(
                warning.startswith(b.get("title", "旧安排") + "：")
                for warning in block_warnings
            )
        ]
        proof = {
            "removed": repair["removed"],
            "warnings": block_warnings,
            "affected": [
                {
                    k: b.get(k)
                    for k in (
                        "id",
                        "task_id",
                        "step_id",
                        "starts_at",
                        "ends_at",
                        "status",
                        "locked",
                    )
                }
                for b in affected
            ],
            "work": [work_basis(b["task_id"], b["step_id"]) for b in affected],
        }
        reasons = list(
            dict.fromkeys([r["reason"] for r in repair["removed"]] + block_warnings)
        )
        add(
            "facts_changed",
            "facts:invalid-plan",
            "已确认事实变化，原安排需要校对",
            reasons,
            5,
            {"replanning": repair, "affected_blocks": affected},
            proof,
        )
    return found, capacity


async def refresh_suggestions(db, owner, app_active=True):
    preference = await read_preferences(db, owner)
    if not preference["data"]["enabled"]:
        return await list_suggestions(db, owner, suppressed="disabled")
    if not app_active:
        return await list_suggestions(db, owner, suppressed="inactive")
    from app.planner import planning_result

    inputs, result = await planning_result(db, owner, repair=True)
    found, capacity = candidates(inputs, result)
    blocks = {r.id: r for r in await store.rows(db, owner, "plan_block")}
    for candidate in found:
        if candidate["category"] == "facts_changed":
            candidate["sources"] = [
                {"id": r.id, "kind": r.kind, "revision": r.revision}
                for block in candidate["evidence"]["affected_blocks"]
                if (r := blocks.get(block["id"]))
            ]
    existing = await store.rows(db, owner, "proactive_suggestion")
    current = {r.data["issue_key"]: r for r in existing if r.data["state"] in ACTIVE}
    keys = {c["issue_key"] for c in found}
    clock = now()
    for key, resource in current.items():
        if key not in keys:
            resource.data = {
                **resource.data,
                "state": "resolved",
                "resolved_at": clock.isoformat(),
            }
            resource.revision += 1
    for candidate in found:
        resource = current.get(candidate["issue_key"])
        if resource and resource.data["fingerprint"] == candidate["fingerprint"]:
            state = resource.data["state"]
            if (
                state == "snoozed"
                and resource.data["snoozed_until"]
                and clock >= datetime.fromisoformat(resource.data["snoozed_until"])
            ):
                state = "pending"
                resource.revision += 1
            resource.data = {**resource.data, **candidate, "state": state}
            continue
        if resource:
            resource.data = {
                **resource.data,
                "state": "superseded",
                "resolved_at": clock.isoformat(),
            }
            resource.revision += 1
        db.add(
            Resource(
                id=str(uuid4()),
                owner_id=owner,
                kind="proactive_suggestion",
                data={
                    "schema_version": 1,
                    **candidate,
                    "state": "pending",
                    "first_seen_at": clock.isoformat(),
                    "snoozed_until": None,
                    "resolved_at": None,
                },
            )
        )
    await db.flush()
    return await list_suggestions(
        db, owner, capacity=capacity, source_revision=inputs["source_revision"]
    )


async def act_on_suggestion(db, owner, rid, body, key):
    # A committed receipt is a historical command result, including after source
    # changes. Replaying it cannot repeat any effect; original draft confirmation
    # independently revalidates current A facts. Never calculate before replay.
    await store.owned(db, owner, rid, "proactive_suggestion")
    payload = body.model_dump(mode="json")
    receipt = await store.replay(db, owner, f"proactive-action:{rid}", key, payload)
    if receipt:
        return receipt.result
    await refresh_suggestions(db, owner)
    resource = await store.owned(db, owner, rid, "proactive_suggestion")
    preference = await read_preferences(db, owner)
    if (
        resource.data["fingerprint"] != body.fingerprint
        or resource.data["state"] not in ACTIVE
        or not preference["data"]["enabled"]
        or not preference["data"]["categories"][resource.data["category"]]
    ):
        raise HTTPException(409, "建议依据或设置已变化，请刷新后重新校对")
    store.revision(resource, body.revision)
    if resource.data["state"] not in {"pending", "snoozed"}:
        raise HTTPException(409, "此建议已处理，请刷新")

    async def operation():
        output = {"open_task_id": None, "draft": None, "requires_confirmation": False}
        if body.action == "snooze":
            resource.data = {
                **resource.data,
                "state": "snoozed",
                "snoozed_until": (
                    now() + timedelta(minutes=body.snooze_minutes)
                ).isoformat(),
            }
        elif body.action == "dismiss":
            resource.data = {**resource.data, "state": "dismissed"}
        elif body.action == "disable_category":
            from app.proactive_contracts import ProactivePreferenceWrite

            data = {
                **preference["data"],
                "categories": {
                    **preference["data"]["categories"],
                    resource.data["category"]: False,
                },
            }
            await write_preferences(
                db,
                owner,
                ProactivePreferenceWrite(revision=preference["revision"], data=data),
            )
            resource.data = {**resource.data, "state": "dismissed"}
        else:
            if body.accept_mode == "details":
                output["open_task_id"] = resource.data.get("task_id")
                if not output["open_task_id"]:
                    raise HTTPException(
                        422, "此建议为整体容量/变更依据，请查看依据或生成待确认草稿"
                    )
                await store.owned(db, owner, output["open_task_id"], "task")
            else:
                from app.planner import PlanRequest
                from app.replanning import replan_draft

                settings = await store.settings(db, owner)
                output["draft"] = await replan_draft(
                    db, owner, PlanRequest(expected_source_revision=settings.revision)
                )
                output["requires_confirmation"] = True
            resource.data = {**resource.data, "state": "accepted"}
        resource.revision += 1
        await record_change(
            db,
            owner,
            "proactive_suggestion_action",
            resource.id,
            resource.revision,
            {
                "action": body.action,
                "category": resource.data["category"],
                "fingerprint": body.fingerprint,
                "draft_id": output["draft"]["id"] if output["draft"] else None,
            },
        )
        await db.flush()
        current_preference = await read_preferences(db, owner)
        return {
            "suggestion": suggestion_view(resource, current_preference["data"]),
            **output,
        }

    return await store.mutate(
        db, owner, f"proactive-action:{rid}", key, payload, operation
    )
