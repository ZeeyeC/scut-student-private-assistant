"""Compare confirmed goal budgets with one shared planner capacity upper bound."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import planner, store
from app.db import now
from app.review_contracts import validate_week


async def read_goal_capacity(
    db, owner, week_start=None, report_timezone=None, expected_source_revision=None
):
    settings = await store.rows(db, owner, "settings")
    cfg = settings[0] if settings else None
    zone_name = cfg.data["timezone"] if cfg else (report_timezone or "Asia/Shanghai")
    try:
        zone = ZoneInfo(zone_name)
        clock = now()
        today = clock.astimezone(zone).date()
        week = week_start or today + timedelta(days=7 - today.weekday())
        validate_week(week, zone_name)
        if datetime.combine(week, time.min, zone) <= clock:
            raise ValueError("请选择尚未开始的完整周")
        if cfg and report_timezone and report_timezone != zone_name:
            raise ValueError("容量使用已保存的排程时区，请先核对设置")
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    revision = cfg.revision if cfg else 0
    if expected_source_revision is not None and expected_source_revision != revision:
        raise HTTPException(409, "资料已变化，请刷新目标容量")
    goals = await store.rows(db, owner, "goal")
    active = [g for g in goals if not g.data["paused"]]
    budget = sum(g.data["weekly_budget_minutes"] for g in active)
    capacity = None
    if cfg:
        _, result = await planner.planning_result(db, owner, target=week, horizon=7)
        capacity = result["capacity"]
    upper = capacity["capacity_upper_bound_minutes"] if capacity else None
    return {
        "contract_version": "goal-capacity-v1",
        "status": "known" if capacity else "unknown",
        "week_start": week.isoformat(),
        "week_end": (week + timedelta(days=7)).isoformat(),
        "timezone": zone_name,
        "source_revision": revision,
        "shared_capacity_upper_bound_minutes": upper,
        "active_weekly_budget_minutes": budget,
        "minimum_deficit_minutes": max(0, budget - upper)
        if upper is not None
        else None,
        "active_goal_ids": [g.id for g in active],
        "paused_goal_ids": [g.id for g in goals if g.data["paused"]],
        "goal_revisions": {g.id: g.revision for g in goals},
        "actual_minutes": None,
        "capacity": capacity,
    }
