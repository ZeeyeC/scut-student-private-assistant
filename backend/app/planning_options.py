"""Read-only comparable plans and risk facts for B's suggestion/negotiation UI."""

from copy import deepcopy
from datetime import date, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from app.constraints import planning_constraints
from app.contracts import StrictModel
from app.planning_facts import profile_windows
from app.replanning import ReplanAddition


def preferred_windows(windows, preferences):
    from app.planner import instant, subtract

    spans = []
    for a, b in windows:
        for row in preferences:
            c, d = instant(row["data"]["starts_at"]), instant(row["data"]["ends_at"])
            if max(a, c) < min(b, d):
                spans.append((max(a, c), min(b, d)))
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged + subtract(windows, merged)


class Option(StrictModel):
    id: Literal["earliest", "preferred"]
    title: str
    proposed_minutes: int
    unallocated_minutes: int
    preferred_minutes: int
    retained_count: int
    changed_count: int
    explanation: list[str]
    blocks: list[ReplanAddition]


class Options(StrictModel):
    schema_version: int = 1
    source_revision: int
    timezone: str
    target_date: date
    horizon_days: int
    preference_count: int
    options: list[Option]
    profile_integration: str = "pending_person_b"
    goal_integration: str = "pending_person_b"
    goal_allocation: dict = {}
    profile_context: dict = {}


class Risk(StrictModel):
    code: Literal["unknown_estimate", "overdue", "unallocated"]
    task_id: str | None = None
    step_id: str | None = None
    title: str
    remaining_minutes: int | None
    reason: str


class Risks(StrictModel):
    schema_version: int = 1
    source_revision: int
    timezone: str
    capacity_upper_bound_minutes: int
    required_minutes: int
    unallocated_minutes: int
    unknown_estimate_count: int
    risks: list[Risk]
    execution_integration: str = "pending_person_b"
    goal_allocation: dict = {}
    execution_context: dict = {}


def compare_plans(inputs):
    from app.planner import build_plan, instant

    preferences = planning_constraints(inputs, "soft") + profile_windows(inputs)[0]
    options = []
    for strategy, title in [("earliest", "更早开始"), ("preferred", "遵循软偏好")]:
        p = {**deepcopy(inputs), "planning_strategy": strategy}
        result = build_plan(p)
        preferred = 0
        for b in result["blocks"]:
            day = (
                instant(b["starts_at"])
                .astimezone(ZoneInfo(inputs["settings"]["timezone"]))
                .date()
            )
            target = date.fromisoformat(inputs["target_date"])
            if (
                not target <= day < target + timedelta(days=inputs["horizon_days"])
                or b["status"] == "completed"
            ):
                continue
            # Subtract the union, so overlapping preferences are not double-counted.
            from app.planner import subtract

            busy = [
                (instant(r["data"]["starts_at"]), instant(r["data"]["ends_at"]))
                for r in preferences
            ]
            total = (
                instant(b["ends_at"]) - instant(b["starts_at"])
            ).total_seconds() / 60
            outside = sum(
                (end - start).total_seconds() / 60
                for start, end in subtract(
                    [(instant(b["starts_at"]), instant(b["ends_at"]))], busy
                )
            )
            preferred += int(total - outside)
        c = result["capacity"]
        options.append(
            Option(
                id=strategy,
                title=title,
                proposed_minutes=c["proposed_minutes"],
                unallocated_minutes=c["unallocated_minutes"],
                preferred_minutes=preferred,
                retained_count=len(result["changes"]["retained_ids"]),
                changed_count=len(result["changes"]["added_ids"])
                + len(result["changes"]["removed_ids"]),
                explanation=[
                    "课程、固定事项、硬禁排、截止、依赖和每日上限均必须满足",
                    "同一天内优先使用已确认软偏好窗口；不满足时可使用其他空档"
                    if strategy == "preferred" and preferences
                    else "按可用时间先后安排；未设置软偏好时两个方案可能相同",
                    "偏好造成少排时已让步，优先保住可排工作量"
                    if result.get("preference_fallback")
                    else "分钟为计划工作量，不是实际投入",
                ],
                blocks=[
                    {k: b[k] for k in ReplanAddition.model_fields}
                    for b in result["blocks"]
                ],
            )
        )
    return Options(
        source_revision=inputs["source_revision"],
        timezone=inputs["settings"]["timezone"],
        target_date=inputs["target_date"],
        horizon_days=inputs["horizon_days"],
        preference_count=len(preferences),
        options=options,
        profile_integration="confirmed_profile_v1"
        if "profile_context" in inputs
        else "pending_person_b",
        goal_integration="goal_budget_v1"
        if "goal_context" in inputs
        else "pending_person_b",
        profile_context=inputs.get("profile_context", {}),
        goal_allocation=result.get("goal_allocation", {}),
    )


def risk_report(inputs, result):
    from app.planner import instant

    tasks = {r["id"]: r["data"] for r in inputs["tasks"]}
    steps = {r["id"]: r["data"] for r in inputs["steps"]}
    risks = []
    for u in result["capacity"]["unscheduled"]:
        tid = u.get("task_id") or steps.get(u.get("step_id"), {}).get("task_id")
        task = tasks.get(tid, {})
        deadline = task.get("remedy_due_at") or task.get("due_at")
        code = (
            "unknown_estimate"
            if u["remaining_minutes"] is None
            else "overdue"
            if deadline and instant(deadline) < instant(inputs["now_utc"])
            else "unallocated"
        )
        risks.append(
            Risk(
                code=code,
                task_id=tid,
                step_id=u.get("step_id"),
                title=u["title"],
                remaining_minutes=u["remaining_minutes"],
                reason=u["reason"],
            )
        )
    c = result["capacity"]
    return Risks(
        source_revision=inputs["source_revision"],
        timezone=c["timezone"],
        capacity_upper_bound_minutes=c["capacity_upper_bound_minutes"],
        required_minutes=c["required_minutes"],
        unallocated_minutes=c["unallocated_minutes"],
        unknown_estimate_count=c["unknown_estimate_count"],
        risks=risks,
        execution_integration=inputs.get("execution_context", {}).get(
            "integration", "pending_person_b"
        ),
        execution_context=inputs.get("execution_context", {}),
        goal_allocation=result.get("goal_allocation", {}),
    )


def option_router(get_db, current_user):
    router = APIRouter()

    @router.get("/planning-options", response_model=Options)
    async def options(
        target_date: date | None = None,
        horizon_days: int = Query(7, ge=1, le=7),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        from app.planner import planning_result

        inputs, _ = await planning_result(
            db, str(user.id), target=target_date, horizon=horizon_days
        )
        return compare_plans(inputs)

    @router.get("/planning-risks", response_model=Risks)
    async def risks(
        target_date: date | None = None,
        horizon_days: int = Query(7, ge=1, le=7),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        from app.planner import planning_result

        inputs, result = await planning_result(
            db, str(user.id), target=target_date, horizon=horizon_days
        )
        return risk_report(inputs, result)

    return router
