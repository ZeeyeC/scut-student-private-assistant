"""A-owned adapters. B's facts stay authoritative and are never rewritten here."""

from copy import deepcopy
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app import execution, goals, profiles, store


async def load_facts(db, owner, inputs):
    inputs = deepcopy(inputs)
    facts = {}
    records = await store.rows(db, owner, "execution")
    effective = execution.effective(records)
    timers = await store.rows(db, owner, "execution_timer")
    for step in inputs["steps"]:
        data = step["data"]
        summary = await execution.execution_summary(
            db, owner, data["task_id"], step["id"]
        )
        observations = [r for r in effective if r.data.get("step_id") == step["id"]]
        # Replace the compatibility projection, never add it to the new facts.
        data["spent_minutes"] = summary.planning_spent_minutes
        facts[step["id"]] = {
            **summary.model_dump(mode="json"),
            "records": [
                {
                    "id": r.id,
                    "revision": r.revision,
                    **{
                        k: r.data.get(k)
                        for k in (
                            "source",
                            "feedback",
                            "unfinished_reason",
                            "actual_minutes",
                            "actual_seconds",
                            "performed_on",
                            "unconfirmed_interval",
                        )
                    },
                }
                for r in observations
            ],
            "timers": [
                {
                    "id": r.id,
                    "revision": r.revision,
                    "status": r.data["status"],
                    "plan_block_id": r.data["target"].get("plan_block_id"),
                }
                for r in timers
                if r.data.get("step_id") == step["id"]
            ],
        }
    task_facts = {}
    for task in inputs["tasks"]:
        summary = await execution.execution_summary(db, owner, task["id"])
        task_facts[task["id"]] = {
            **summary.model_dump(mode="json"),
            "task_status": task["data"]["status"],
            "unassigned_record_ids": [
                r.id
                for r in effective
                if r.data["task_id"] == task["id"] and not r.data.get("step_id")
            ],
        }
    inputs["execution_context"] = {
        "integration": "authoritative_execution_v1",
        "steps": facts,
        "tasks": task_facts,
        "actual_minutes": sum(f["actual_minutes"] or 0 for f in task_facts.values())
        if task_facts
        and all(
            f["actual_minutes"] is not None and not f["unknown_step_ids"]
            for f in task_facts.values()
        )
        else None,
        "known_actual_minutes": sum(
            f["actual_minutes"] or 0 for f in task_facts.values()
        ),
        "unknown_step_ids": [
            sid for sid, f in facts.items() if sid in f["unknown_step_ids"]
        ],
    }
    inputs["profile_context"] = await profiles.read_profile(db, owner)
    from app.study_types import classifications

    inputs["study_classifications"] = await classifications(db, owner)
    inputs["profile_context"]["application"] = {
        "supported_fields": [
            "preferred_study_windows.any/deep/review（匹配已确认任务类型）",
            "energy_windows",
            "focus_minutes",
            "break_minutes",
            "daily_load_minutes",
            "leisure_protection",
            "review_interval_days（显式复习候选）",
        ],
        "configured_fields": [
            key
            for key, value in inputs["profile_context"]["data"]["preferences"].items()
            if value is not None and value != []
        ],
        "deferred_fields": {},
        "classification_count": sum(
            len(rows) for rows in inputs["study_classifications"].values()
        ),
        "active_at_planning_time": bool(active_profile(inputs, inputs["now_utc"])),
        "semantics": "仅已确认且在有效期内的偏好参与；不是新增永久禁排规则",
    }
    inputs["goal_context"] = await goals.read_goals(db, owner)
    # Needed to count observed weekly effort once in the goal allocation adapter.
    inputs["effective_executions"] = [store.view(r) for r in effective]
    return inputs


def active_profile(p, instant):
    context = p.get("profile_context", {})
    data = context.get("data", {})
    if not data.get("confirmed") or not data.get("timezone"):
        return {}
    day = instant.astimezone(ZoneInfo(data["timezone"])).date().isoformat()
    if data.get("effective_from") and day < data["effective_from"]:
        return {}
    if data.get("effective_until") and day > data["effective_until"]:
        return {}
    return data


def profile_windows(p, task_type="any"):
    from app.constraints import local_instant
    from app.planner import instant

    data = p.get("profile_context", {}).get("data", {})
    if not data.get("confirmed") or not data.get("timezone"):
        return [], []
    zone = ZoneInfo(data["timezone"])
    planning_zone = ZoneInfo(p["settings"]["timezone"])
    start = datetime.combine(
        date.fromisoformat(p["target_date"]), time.min, planning_zone
    )
    end = start + timedelta(days=p["horizon_days"])
    day = start.astimezone(zone).date()
    last = end.astimezone(zone).date()
    preferred, low_energy = [], []
    prefs = data["preferences"]
    windows = [
        (index, r, "preferred")
        for index, r in enumerate(prefs.get("preferred_study_windows") or [])
        if r["task_type"] in ("any", task_type)
    ]
    windows += [
        (f"energy:{index}", r, r["level"])
        for index, r in enumerate(prefs.get("energy_windows") or [])
    ]
    while day <= last:
        for index, row, kind in windows:
            if day.isoweekday() not in row["weekdays"]:
                continue
            a = local_instant(
                datetime.combine(day, time.fromisoformat(row["start"])), zone
            )
            b = local_instant(
                datetime.combine(day, time.fromisoformat(row["end"])), zone
            )
            if not active_profile(p, a) or b <= instant(start) or a >= instant(end):
                continue
            item = {
                "id": f"profile:{p['profile_context']['id']}:{day}:{index}",
                "revision": p["profile_context"]["revision"],
                "data": {"starts_at": a.isoformat(), "ends_at": b.isoformat()},
            }
            if kind in ("preferred", "high"):
                preferred.append(item)
            elif kind == "low":
                low_energy.append(item)
        day += timedelta(days=1)
    return preferred, low_energy


def profile_limits(p, start, blocks):
    """Soft personal limits are evaluated in the profile's own local day."""
    from app.planner import instant

    data = active_profile(p, start)
    prefs = data.get("preferences", {})
    cap = prefs.get("daily_load_minutes")
    if cap is not None:
        zone = ZoneInfo(data["timezone"])
        day = start.astimezone(zone).date()
        a = instant(datetime.combine(day, time.min, zone))
        b = instant(datetime.combine(day + timedelta(days=1), time.min, zone))
        used = sum(
            max(
                0,
                (
                    min(b, instant(r["ends_at"])) - max(a, instant(r["starts_at"]))
                ).total_seconds(),
            )
            / 60
            for r in blocks
        )
        cap = max(0, cap - used)
    return cap, prefs.get("focus_minutes"), prefs.get("break_minutes") or 0


def goal_inputs(p):
    """One work item belongs to one budget, selected deterministically, not twice."""
    active = [
        g for g in p.get("goal_context", {}).get("goals", []) if not g["data"]["paused"]
    ]
    active.sort(
        key=lambda g: (
            -g["data"]["priority"],
            g["data"].get("deadline") or "9999",
            g["id"],
        )
    )
    by_task = {}
    for goal in active:
        for sub in goal["data"]["subtasks"]:
            if sub.get("task_id") and sub["status"] == "open":
                by_task.setdefault(sub["task_id"], goal["id"])
    return {g["id"]: g for g in active}, by_task


def week_key(value, zone):
    d = value.astimezone(zone).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def observed_goal_usage(p, task_goals, zone):
    usage = {}
    for row in p.get("effective_executions", []):
        data = row["data"]
        gid = task_goals.get(data["task_id"])
        if not gid:
            continue
        if data.get("unconfirmed_interval"):
            continue
        # A reported date is not a made-up timestamp. If its possible instants
        # span two planning weeks, leave attribution unknown instead of guessing.
        day = datetime.combine(
            date.fromisoformat(data["performed_on"]),
            time.min,
            ZoneInfo(data["timezone"]),
        )
        week = week_key(day, zone)
        if week != week_key(day + timedelta(days=1) - timedelta(microseconds=1), zone):
            continue
        key = (gid, week)
        usage[key] = (
            usage.get(key, 0)
            + data.get("actual_seconds", data["actual_minutes"] * 60) / 60
        )
    return usage


def goal_report(p, result, task_goals, active):
    from app.planner import instant

    zone = ZoneInfo(p["settings"]["timezone"])
    observed = observed_goal_usage(p, task_goals, zone)
    weeks = sorted(
        {
            week_key(
                datetime.combine(
                    date.fromisoformat(p["target_date"]) + timedelta(days=i),
                    time.min,
                    zone,
                ),
                zone,
            )
            for i in range(p["horizon_days"])
        }
    )
    rows = []
    for week in weeks:
        for gid, goal in active.items():
            allocated = sum(
                (instant(b["ends_at"]) - instant(b["starts_at"])).total_seconds() / 60
                for b in result["blocks"]
                if task_goals.get(b["task_id"]) == gid
                and b["status"] != "completed"
                and instant(b["ends_at"]) > instant(p["now_utc"])
                and week_key(instant(b["starts_at"]), zone) == week
            )
            known = observed.get((gid, week), 0)
            rows.append(
                {
                    "goal_id": gid,
                    "goal_revision": goal["revision"],
                    "week_start": week,
                    "weekly_budget_minutes": goal["data"]["weekly_budget_minutes"],
                    "known_actual_minutes": known,
                    "planned_minutes": int(allocated),
                    "unmet_budget_minutes": max(
                        0,
                        goal["data"]["weekly_budget_minutes"] - known - int(allocated),
                    ),
                    "allowed_adjustment": goal["data"]["allowed_adjustment"],
                    "load_category": goal["data"].get("load_category", "unknown"),
                    "actual_total_known": False,
                    "reason": "仅分配已关联的真实待办；未知投入不计为0，不为填满预算虚构任务",
                }
            )
    return {
        "integration": "goal_budget_v1",
        "task_goal_ids": task_goals,
        "weeks": rows,
        "paused_goal_ids": [
            g["id"]
            for g in p.get("goal_context", {}).get("goals", [])
            if g["data"]["paused"]
        ],
        "dedupe_rule": "每项任务按目标优先级/截止/ID归入一个活动目标；暂停目标的既有任务仍可独立排程",
    }
