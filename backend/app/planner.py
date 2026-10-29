from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field, model_validator

from app import imports, store
from app.calendar import expand_calendar, occupied_course_events
from app.constraints import planning_constraints
from app.contracts import ResourceView, StrictModel
from app.db import Resource, now
from app.planning_capacity import CapacityReport, capacity_report
from app.planning_facts import (
    active_profile,
    goal_inputs,
    goal_report,
    load_facts,
    observed_goal_usage,
    profile_limits,
    profile_windows,
    week_key,
)
from app.planning_history import PLANNER_RULE_VERSION, save_snapshot


def instant(value):
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not dt.tzinfo:
        raise ValueError("时间必须带时区")
    return dt.astimezone(timezone.utc)


def subtract(windows, busy):
    for bs, be in sorted(busy):
        new = []
        for a, b in windows:
            if be <= a or bs >= b:
                new.append((a, b))
            else:
                if a < bs:
                    new.append((a, bs))
                if be < b:
                    new.append((be, b))
        windows = new
    return windows


def protected_today_block(p, block):
    """Today's action must not change history, ongoing work or another date."""
    if block["id"] in p.get("timer_protected_ids", []) or instant(
        block["starts_at"]
    ) < instant(p["now_utc"]):
        return True
    if p.get("scope") != "today" and not p.get("repair"):
        return False
    tz = ZoneInfo(p["settings"]["timezone"])
    if p.get("repair"):
        day = instant(block["starts_at"]).astimezone(tz).date()
        target = date.fromisoformat(p["target_date"])
        return not target <= day < target + timedelta(
            days=p["horizon_days"]
        ) or instant(block["starts_at"]) < instant(p["now_utc"])
    return instant(block["starts_at"]).astimezone(tz).date().isoformat() != p[
        "target_date"
    ] or instant(block["starts_at"]) < instant(p["now_utc"])


def revalidate_preserved(p, clock, tz):
    """Old suggestions are not evidence of capacity after domain facts change."""
    cfg = p["settings"]
    steps = {s["id"]: s["data"] for s in p["steps"]}
    tasks = {t["id"]: t["data"] for t in p["tasks"]}
    buffer = timedelta(minutes=cfg["buffer_minutes"])
    busy = [
        (instant(e["starts_at"]) - buffer, instant(e["ends_at"]) + buffer)
        for e in occupied_course_events(p["occurrences"]) + p["fixed_events"]
    ]
    protected = planning_constraints(p)
    busy.extend(
        (instant(r["data"]["starts_at"]), instant(r["data"]["ends_at"]))
        for r in protected
    )
    kept, removed, warnings, invalid_locked = [], [], [], set()
    minutes_by_day, allocated = {}, {}
    for block in sorted(
        p["preserved_blocks"],
        key=lambda b: (not b.get("locked"), b["starts_at"], b["id"]),
    ):
        a, b = instant(block["starts_at"]), instant(block["ends_at"])
        if block["status"] == "completed" or b <= clock:
            kept.append(block)
            if b > clock:
                busy.append((a, b))
            continue
        step = steps.get(block["step_id"], {})
        task = tasks.get(block["task_id"], {})
        d = a.astimezone(tz).date()
        n = int((b - a).total_seconds() // 60)
        deadline = task.get("remedy_due_at") or task.get("due_at")
        windows = [
            (
                instant(datetime.combine(d, time.fromisoformat(w["start"]), tz)),
                instant(datetime.combine(d, time.fromisoformat(w["end"]), tz)),
            )
            for w in cfg["study_windows"]
        ]
        reason = None
        if task.get("status") != "open" or step.get("status") != "open":
            reason = "任务或步骤状态已变更"
        elif deadline and b > instant(deadline):
            reason = "已超过更新后的截止时间"
        elif a < clock:
            reason = "尚未完成的时间块已经开始，请先记录实际投入"
        elif any(
            a < instant(r["data"]["ends_at"]) and b > instant(r["data"]["starts_at"])
            for r in protected
        ):
            reason = "与已确认的禁排时段冲突"
        elif any(a < end and b > start for start, end in busy):
            reason = "与课程、固定事项或保留安排冲突"
        elif not any(start <= a and b <= end for start, end in windows):
            reason = "已不在学习窗口内"
        elif (
            n > cfg["max_block_minutes"]
            or minutes_by_day.get(d, 0) + n > cfg["daily_limit_minutes"]
        ):
            reason = "超过更新后的学习上限"
        elif allocated.get(block["step_id"], 0) + n > max(
            0, (step.get("estimated_minutes") or 0) - step.get("spent_minutes", 0)
        ):
            reason = "超过步骤剩余耗时"
        if reason:
            warnings.append(
                f"{block.get('title', '旧安排')}：{reason}；"
                + (
                    "请解锁后重新规划"
                    if block.get("locked")
                    else "本次原样保留，请单独检查此安排"
                    if protected_today_block(p, block)
                    else "确认计划时移除旧建议"
                )
            )
            if block.get("locked") or protected_today_block(p, block):
                invalid_locked.add(block["step_id"])
                kept.append(block)
                busy.append((a, b))
            else:
                removed.append(
                    {
                        "id": block["id"],
                        "title": block.get("title", "旧安排"),
                        "reason": reason,
                    }
                )
            continue
        kept.append(block)
        busy.append((a, b))
        minutes_by_day[d] = minutes_by_day.get(d, 0) + n
        allocated[block["step_id"]] = allocated.get(block["step_id"], 0) + n
    # A retained dependent cannot precede the work that unlocks it. Suggestions
    # that need replacement are shown as removals. Today mode instead reports
    # conflicts outside its editable scope while preserving those exact facts.
    changed = True
    while changed:
        changed = False
        for block in list(kept):
            if (
                block["status"] == "completed"
                or instant(block["ends_at"]) <= clock
                or block["step_id"] in invalid_locked
            ):
                continue
            for dep in steps[block["step_id"]]["dependency_ids"]:
                if steps[dep]["status"] == "completed":
                    continue
                ready = sum(
                    (instant(x["ends_at"]) - instant(x["starts_at"])).total_seconds()
                    / 60
                    for x in kept
                    if x["step_id"] == dep
                    and dep not in invalid_locked
                    and x["status"] != "completed"
                    and instant(x["ends_at"]) <= instant(block["starts_at"])
                    and instant(x["ends_at"]) > clock
                )
                if ready < max(
                    0,
                    (steps[dep]["estimated_minutes"] or 0)
                    - steps[dep]["spent_minutes"],
                ):
                    reason = "旧安排的前置步骤未在开始前满足"
                    warnings.append(f"{block.get('title', '旧安排')}：{reason}")
                    if block.get("locked") or protected_today_block(p, block):
                        invalid_locked.add(block["step_id"])
                    else:
                        kept.remove(block)
                        removed.append(
                            {
                                "id": block["id"],
                                "title": block.get("title", "旧安排"),
                                "reason": reason,
                            }
                        )
                    changed = True
                    break
    return kept, removed, warnings, invalid_locked


def build_plan(p):
    cfg = p["settings"]
    tz = ZoneInfo(cfg["timezone"])
    clock = instant(p["now_utc"])
    start = date.fromisoformat(p["target_date"])
    days = p["horizon_days"]
    if start < clock.astimezone(tz).date() or not 1 <= days <= 7:
        raise ValueError("只能规划今日起 1–7 天")
    if p.get("scope") == "today" and (
        start != clock.astimezone(tz).date() or days != 1
    ):
        raise ValueError("当日模式只能规划当前时区的今天")
    preserved, removed, warnings, invalid_locked = revalidate_preserved(p, clock, tz)
    blocks = list(preserved)
    unscheduled = []
    busy = []
    buffer = timedelta(minutes=cfg["buffer_minutes"])
    for e in occupied_course_events(p["occurrences"]) + p["fixed_events"]:
        busy.append((instant(e["starts_at"]) - buffer, instant(e["ends_at"]) + buffer))
    protected = planning_constraints(p)
    busy.extend(
        (instant(r["data"]["starts_at"]), instant(r["data"]["ends_at"]))
        for r in protected
    )
    busy.extend((instant(b["starts_at"]), instant(b["ends_at"])) for b in preserved)
    for block in preserved:
        personal = active_profile(p, instant(block["starts_at"]))
        rest = personal.get("preferences", {}).get("break_minutes") or 0
        if rest:
            busy.append(
                (
                    instant(block["starts_at"]) - timedelta(minutes=rest),
                    instant(block["ends_at"]) + timedelta(minutes=rest),
                )
            )
    free = {}
    used = {}
    for i in range(days):
        d = start + timedelta(days=i)
        windows = []
        for w in cfg["study_windows"]:
            a = instant(datetime.combine(d, time.fromisoformat(w["start"]), tz))
            b = instant(datetime.combine(d, time.fromisoformat(w["end"]), tz))
            a = max(
                a,
                clock.replace(second=0, microsecond=0)
                + (
                    timedelta(minutes=1)
                    if clock.second or clock.microsecond
                    else timedelta()
                ),
            )
            if a < b:
                windows.append((a, b))
        free[d] = subtract(sorted(windows), busy)
        used[d] = sum(
            (instant(b["ends_at"]) - instant(b["starts_at"])).total_seconds() / 60
            for b in preserved
            if instant(b["starts_at"]).astimezone(tz).date() == d
        )
    capacity_free = {d: list(windows) for d, windows in free.items()}
    preferences = planning_constraints(p, "soft")
    personal_windows, low_energy = profile_windows(p)
    preferences += personal_windows
    if p.get("planning_strategy") == "preferred":
        from app.planning_options import preferred_windows

        for d in free:
            if low_energy:
                low_spans = [
                    (instant(r["data"]["starts_at"]), instant(r["data"]["ends_at"]))
                    for r in low_energy
                ]
                good = subtract(free[d], low_spans)
                free[d] = good + subtract(free[d], good)
            profile = active_profile(p, datetime.combine(d, time(12), tz))
            if (
                profile.get("preferences", {}).get("leisure_protection")
                == "prefer_protect"
            ):
                free[d].sort(key=lambda w: (-(w[1] - w[0]).total_seconds(), w[0]))
            free[d] = preferred_windows(free[d], preferences)
    capacity_used = dict(used)
    all_steps = {s["id"]: s["data"] for s in p["steps"]}
    tasks = {t["id"]: t["data"] for t in p["tasks"] if t["data"]["status"] == "open"}
    done = {k for k, v in all_steps.items() if v["status"] == "completed"}
    finish = {k: clock for k in done}
    assigned = {}
    locked_finish = {}
    for b in preserved:
        if (
            b["status"] != "completed"
            and instant(b["ends_at"]) > clock
            and b["step_id"] not in invalid_locked
        ):
            minutes = (
                instant(b["ends_at"]) - instant(b["starts_at"])
            ).total_seconds() / 60
            assigned[b["step_id"]] = assigned.get(b["step_id"], 0) + minutes
            locked_finish[b["step_id"]] = max(
                locked_finish.get(b["step_id"], clock), instant(b["ends_at"])
            )
    remaining = {
        k: max(0, v["estimated_minutes"] - v["spent_minutes"] - assigned.get(k, 0))
        for k, v in all_steps.items()
        if v["task_id"] in tasks
        and v["status"] == "open"
        and v["estimated_minutes"] is not None
    }
    required_minutes = sum(remaining.values())
    active_goals, task_goals = goal_inputs(p)
    goal_used = observed_goal_usage(p, task_goals, tz)
    for block in preserved:
        gid = task_goals.get(block["task_id"])
        if gid and block["status"] != "completed" and instant(block["ends_at"]) > clock:
            key = (gid, week_key(instant(block["starts_at"]), tz))
            goal_used[key] = (
                goal_used.get(key, 0)
                + (
                    instant(block["ends_at"]) - instant(block["starts_at"])
                ).total_seconds()
                / 60
            )

    def due(t):
        task_deadline = (
            instant(t.get("remedy_due_at") or t["due_at"])
            if t.get("remedy_due_at") or t.get("due_at")
            else datetime.max.replace(tzinfo=timezone.utc)
        )
        return task_deadline

    def step_due(sid):
        task = tasks[all_steps[sid]["task_id"]]
        goal = active_goals.get(task_goals.get(all_steps[sid]["task_id"]), {}).get(
            "data", {}
        )
        return min(
            due(task),
            instant(goal["deadline"])
            if goal.get("deadline")
            else datetime.max.replace(tzinfo=timezone.utc),
        )

    pending = sorted(
        remaining,
        key=lambda k: (
            step_due(k),
            -active_goals.get(task_goals.get(all_steps[k]["task_id"]), {})
            .get("data", {})
            .get("priority", 0),
            -tasks[all_steps[k]["task_id"]].get("priority", 2),
            all_steps[k]["task_id"],
            k,
        ),
    )
    while pending:
        progressed = False
        for sid in list(pending):
            s = all_steps[sid]
            t = tasks[s["task_id"]]
            deadline = step_due(sid)
            gid = task_goals.get(s["task_id"])
            goal = active_goals.get(gid, {}).get("data", {})
            if sid in invalid_locked:
                unscheduled.append(
                    {
                        "step_id": sid,
                        "remaining_minutes": remaining[sid],
                        "reason": "保留安排需要核对，请先处理警告后重新规划"
                        if p.get("scope") == "today" or p.get("repair")
                        else "锁定安排与当前约束冲突，请先解锁并重新规划",
                    }
                )
                pending.remove(sid)
                progressed = True
                continue
            if deadline < clock:
                unscheduled.append(
                    {
                        "step_id": sid,
                        "remaining_minutes": remaining[sid],
                        "reason": "已逾期，请先设置补救截止日",
                    }
                )
                pending.remove(sid)
                progressed = True
                continue
            if any(dep not in done for dep in s["dependency_ids"]):
                continue
            earliest = max([clock] + [finish[d] for d in s["dependency_ids"]])
            last = max(earliest, locked_finish.get(sid, clock))
            before = (
                len(blocks),
                {d: list(w) for d, w in free.items()},
                dict(used),
                dict(goal_used),
                remaining[sid],
            )
            for d in free:
                for a, b in list(free[d]):
                    a = max(a, earliest)
                    b = min(b, deadline)
                    while remaining[sid] > 0 and a < b:
                        live = [
                            (max(a, x), min(b, y))
                            for x, y in free[d]
                            if max(a, x) < min(b, y)
                        ]
                        if not live:
                            break
                        a, limit = min(live)
                        limit = min(b, limit)
                        personal = active_profile(p, a)
                        personal_midnight = None
                        if personal:
                            personal_zone = ZoneInfo(personal["timezone"])
                            personal_midnight = instant(
                                datetime.combine(
                                    a.astimezone(personal_zone).date()
                                    + timedelta(days=1),
                                    time.min,
                                    personal_zone,
                                )
                            )
                            limit = min(limit, personal_midnight)
                        cap = cfg["daily_limit_minutes"] - used[d]
                        personal_cap, focus, rest = profile_limits(p, a, blocks)
                        if personal_cap is not None:
                            cap = min(cap, personal_cap)
                            if cap <= 0 and personal_midnight and personal_midnight < b:
                                a = personal_midnight
                                continue
                        week = week_key(a, tz)
                        if gid:
                            goal_cap = max(
                                0,
                                goal["weekly_budget_minutes"]
                                - goal_used.get((gid, week), 0),
                            )
                            if (
                                goal["allowed_adjustment"] == "ask"
                                and remaining[sid] > goal_cap
                            ):
                                break
                            cap = min(cap, goal_cap)
                        available = int((limit - a).total_seconds() // 60)
                        n = int(
                            min(
                                remaining[sid],
                                cfg["max_block_minutes"],
                                available,
                                cap,
                                max(cfg["min_block_minutes"], focus)
                                if focus is not None
                                else cfg["max_block_minutes"],
                            )
                        )
                        if (
                            available < cfg["min_block_minutes"]
                            or n <= 0
                            or (n < cfg["min_block_minutes"] and n < remaining[sid])
                        ):
                            break
                        end = a + timedelta(minutes=n)
                        identity = f"{PLANNER_RULE_VERSION}:{p['source_revision']}:{sid}:{a.isoformat()}:{end.isoformat()}"
                        blocks.append(
                            {
                                "id": str(uuid5(NAMESPACE_URL, identity)),
                                "task_id": s["task_id"],
                                "step_id": sid,
                                "title": f"{t.get('title', '作业')} · {s.get('title', '步骤')}",
                                "starts_at": a.isoformat(),
                                "ends_at": end.isoformat(),
                                "locked": False,
                                "status": "suggested",
                                "explanation": {
                                    "rule_version": PLANNER_RULE_VERSION,
                                    "task_id": s["task_id"],
                                    "step_id": sid,
                                    "dependency_ids": s["dependency_ids"],
                                    "settings_revision": p["source_revision"],
                                    "execution_basis": p.get("execution_context", {})
                                    .get("steps", {})
                                    .get(sid),
                                    "profile_revision": p.get(
                                        "profile_context", {}
                                    ).get("revision", 0),
                                    "goal_id": gid,
                                    "constraint_revisions": {
                                        r.get("constraint_id", r["id"]): r["revision"]
                                        for r in protected
                                    },
                                    "reasons": [
                                        f"使用已设置的学习窗口；当天学习上限 {cfg['daily_limit_minutes']} 分钟",
                                        f"本次分配 {n} 分钟，依据步骤剩余耗时和单块上限",
                                        "避开固定课程、事项及已确认禁排时段",
                                    ]
                                    + (
                                        [
                                            "依据已确认档案的专注、休息和负荷偏好；偏好不是永久禁排"
                                        ]
                                        if active_profile(p, a)
                                        else []
                                    )
                                    + (
                                        [
                                            f"属于目标 {active_goals[gid]['data']['title']}；共享周预算只计算一次"
                                        ]
                                        if gid
                                        else []
                                    )
                                    + (
                                        [
                                            "实际投入未知，沿用明确标识的估算/剩余工作，不把缺记录记为0"
                                        ]
                                        if p.get("execution_context", {})
                                        .get("steps", {})
                                        .get(sid, {})
                                        .get("actual_minutes", 0)
                                        is None
                                        else []
                                    )
                                    + (
                                        [
                                            "优先使用已确认软偏好窗口"
                                            if not subtract(
                                                [(a, end)],
                                                [
                                                    (
                                                        instant(r["data"]["starts_at"]),
                                                        instant(r["data"]["ends_at"]),
                                                    )
                                                    for r in preferences
                                                ],
                                            )
                                            else "偏好窗口不足，使用其他可用时间；硬约束仍满足"
                                        ]
                                        if p.get("planning_strategy") == "preferred"
                                        and preferences
                                        else []
                                    )
                                    + (
                                        [
                                            f"在任务截止 {deadline.astimezone(tz).isoformat()} 前安排"
                                        ]
                                        if deadline.year < 9999
                                        else []
                                    ),
                                },
                            }
                        )
                        free[d] = subtract(free[d], [(a, end)])
                        remaining[sid] -= n
                        used[d] += n
                        if gid:
                            goal_used[(gid, week)] = goal_used.get((gid, week), 0) + n
                        last = max(last, end)
                        a = end + timedelta(minutes=rest)
                        if rest:
                            for rest_day in free:
                                free[rest_day] = subtract(
                                    free[rest_day],
                                    [(end - timedelta(minutes=n + rest), a)],
                                )
                if remaining[sid] <= 0:
                    break
            if remaining[sid] <= 0:
                done.add(sid)
                finish[sid] = last
            else:
                if gid and goal["allowed_adjustment"] == "ask":
                    count, free, used, goal_used, remaining[sid] = before
                    del blocks[count:]
                unscheduled.append(
                    {
                        "step_id": sid,
                        "remaining_minutes": remaining[sid],
                        "reason": (
                            "今天剩余容量不足、每日上限或无可用时间；未自动延至明天"
                            if p.get("scope") == "today"
                            else "截止前容量不足、每日上限或无可用时间"
                        )
                        + ("（已避让确认的禁排时段）" if protected else ""),
                    }
                )
                if gid:
                    unscheduled[-1]["reason"] += (
                        "；目标预算或共享容量不足，需询问后决定取舍"
                        if goal["allowed_adjustment"] == "ask"
                        else "；按目标周预算减负，未修改截止时间"
                        if goal["allowed_adjustment"] == "reduce"
                        else "；目标允许延后，仅建议在后续可行范围重排，未延长截止时间"
                    )
            pending.remove(sid)
            progressed = True
        if not progressed:
            unscheduled.extend(
                {
                    "step_id": sid,
                    "remaining_minutes": remaining[sid],
                    "reason": "依赖未满足",
                }
                for sid in pending
            )
            break
    for item in unscheduled:
        item["title"] = all_steps[item["step_id"]].get("title", "待完成步骤")
    unscheduled.extend(
        {
            "step_id": sid,
            "title": step.get("title", "待完成步骤"),
            "remaining_minutes": None,
            "reason": "步骤预计耗时未知，请先确认耗时；不把未知当作0",
        }
        for sid, step in all_steps.items()
        if step["task_id"] in tasks
        and step["status"] == "open"
        and step.get("estimated_minutes") is None
    )
    for tid, task in tasks.items():
        if not any(s["task_id"] == tid for s in all_steps.values()):
            unscheduled.append(
                {
                    "task_id": tid,
                    "title": task.get("title", "待办"),
                    "remaining_minutes": None,
                    "reason": "尚无可排程步骤，请填写预计耗时或确认任务拆解",
                }
            )
    # Preserve stable identities for unchanged slots and make replacements visible.
    current = p.get("current_blocks", [])
    old_slots = {
        (b["step_id"], instant(b["starts_at"]), instant(b["ends_at"])): b
        for b in current
    }
    old_ids = {b["id"] for b in current}
    for block in blocks:
        old = old_slots.get(
            (block["step_id"], instant(block["starts_at"]), instant(block["ends_at"]))
        )
        if old and block["id"] not in old_ids:
            block["id"] = old["id"]
    new_ids = {b["id"] for b in blocks}
    horizon_end = instant(datetime.combine(start + timedelta(days=days), time.min, tz))
    horizon_start = instant(datetime.combine(start, time.min, tz))
    for old in current:
        if old["id"] not in new_ids and not any(x["id"] == old["id"] for x in removed):
            removed.append(
                {
                    "id": old["id"],
                    "title": old.get("title", "旧安排"),
                    "starts_at": old["starts_at"],
                    "ends_at": old["ends_at"],
                    "reason": "按当前课程、任务和禁排约束重新计算，确认后替换旧安排",
                }
            )
    result = {
        "blocks": blocks,
        "fixed_agenda": [
            {
                "title": e.get("title", "课程或固定事项"),
                "starts_at": e["starts_at"],
                "ends_at": e["ends_at"],
            }
            for e in occupied_course_events(p["occurrences"]) + p["fixed_events"]
            if instant(e["starts_at"])
            < instant(datetime.combine(start + timedelta(days=days), time.min, tz))
            and instant(e["ends_at"]) > instant(datetime.combine(start, time.min, tz))
        ],
        "unscheduled": unscheduled,
        "warnings": warnings,
        "source_revision": p["source_revision"],
        "timezone": cfg["timezone"],
        "removed_blocks": removed,
        "rule_version": PLANNER_RULE_VERSION,
        "planning_strategy": p.get("planning_strategy", "earliest"),
        "preference_windows": preferences,
        "execution_context": p.get("execution_context", {}),
        "profile_context": p.get("profile_context", {}),
        "protected_windows": [
            r
            for r in protected
            if instant(r["data"]["starts_at"]) < horizon_end
            and instant(r["data"]["ends_at"]) > horizon_start
        ],
        "changes": {
            "added_ids": [b["id"] for b in blocks if b["id"] not in old_ids],
            "retained_ids": [b["id"] for b in blocks if b["id"] in old_ids],
            "removed_ids": [b["id"] for b in removed],
        },
    }
    result["goal_allocation"] = goal_report(p, result, task_goals, active_goals)
    result["capacity"] = capacity_report(
        p,
        result,
        capacity_free,
        capacity_used,
        required_minutes,
        sum(assigned.values()),
        preserved,
        tz,
    )
    if (
        p.get("planning_strategy") == "preferred"
        and result["capacity"]["unallocated_minutes"]
    ):
        # Soft preference boundaries must not strand work that the same hard
        # constraints permit in a continuous window. Prefer feasible work first.
        fallback = build_plan({**p, "planning_strategy": "earliest"})
        if (
            fallback["capacity"]["unallocated_minutes"]
            < result["capacity"]["unallocated_minutes"]
        ):
            fallback["planning_strategy"] = "preferred"
            fallback["preference_fallback"] = True
            old_ids = {
                b["id"]
                for b in p.get("current_blocks", []) + p.get("preserved_blocks", [])
            }
            for b in fallback["blocks"]:
                if b["id"] not in old_ids and b.get("explanation"):
                    b["explanation"]["reasons"].append(
                        "软偏好造成碎片或少排时让步，优先保住所能完成的工作量"
                    )
            return fallback
    return result


class PlanRequest(StrictModel):
    scope: Literal["range", "today"] = "range"
    target_date: date | None = None
    horizon_days: int = Field(default=7, ge=1, le=7)
    strategy: Literal["earliest", "preferred"] = "earliest"
    expected_source_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def today_scope(self):
        if self.scope == "today" and (
            self.target_date is not None
            or ("horizon_days" in self.model_fields_set and self.horizon_days != 1)
        ):
            raise ValueError("当日模式由设置时区确定今天，请勿指定其他日期或多天范围")
        return self


class BlockUpdate(StrictModel):
    revision: int
    locked: bool | None = None
    completed: bool | None = None


async def planning_result(
    db, owner, target=None, horizon=7, scope="range", repair=False, strategy="earliest"
):
    """Same inputs and deterministic calculation for reports and saved drafts."""
    settings = await store.settings(db, owner)
    clock = now()
    tz = ZoneInfo(settings.data["timezone"])
    if scope == "today":
        target, horizon = clock.astimezone(tz).date(), 1
    target = target or clock.astimezone(tz).date()
    courses = [store.view(r) for r in await store.rows(db, owner, "course")]
    blocks = await store.rows(db, owner, "plan_block")
    timer_ids = {
        t.data["target"].get("plan_block_id")
        for t in await store.rows(db, owner, "execution_timer")
        if t.data["status"] not in ("finished", "discarded")
    }
    dates = [
        instant(b.data["starts_at"]).astimezone(tz).date()
        for b in blocks
        if instant(b.data["ends_at"]) > clock
    ]
    try:
        occurrences = expand_calendar(
            settings.data,
            courses,
            [r.data for r in await store.rows(db, owner, "exception")],
            min([target] + dates),
            max([target + timedelta(days=horizon - 1)] + dates),
        )
        preserved = [
            {"id": b.id, **b.data}
            for b in blocks
            if repair
            or b.id in timer_ids
            or b.data.get("locked")
            or b.data["status"] == "completed"
            or instant(b.data["starts_at"]) < clock
            or not target
            <= instant(b.data["starts_at"]).astimezone(tz).date()
            < target + timedelta(days=horizon)
        ]
        inputs = {
            "scope": scope,
            "timer_protected_ids": sorted(x for x in timer_ids if x),
            "repair": repair,
            "planning_strategy": strategy,
            "now_utc": clock,
            "target_date": target.isoformat(),
            "horizon_days": horizon,
            "settings": settings.data,
            "occurrences": occurrences,
            "fixed_events": [
                r.data for r in await store.rows(db, owner, "fixed_event")
            ],
            "tasks": [store.view(r) for r in await store.rows(db, owner, "task")],
            "steps": [store.view(r) for r in await store.rows(db, owner, "step")],
            "preserved_blocks": preserved,
            "source_revision": settings.revision,
            "constraints": [
                store.view(r)
                for r in await store.rows(db, owner, "scheduling_constraint")
            ],
            "current_blocks": [{"id": b.id, **b.data} for b in blocks],
        }
        inputs = await load_facts(db, owner, inputs)
        result = build_plan(inputs)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return inputs, result


async def generate_plan(
    db, owner, target=None, horizon=7, scope="range", strategy="earliest"
):
    inputs, result = await planning_result(
        db, owner, target, horizon, scope, strategy=strategy
    )
    payload = {
        **result,
        "scope": scope,
        "target_date": inputs["target_date"],
        "horizon_days": inputs["horizon_days"],
    }
    return await imports.create_draft(
        db,
        owner,
        "plan",
        payload,
        {
            "planning_inputs": {**inputs, "now_utc": inputs["now_utc"].isoformat()},
            "generated_hash": store.digest(payload),
        },
    )


async def save_plan(db, owner, draft, payload):
    if payload.get("rule_version") != PLANNER_RULE_VERSION:
        raise HTTPException(409, "排程规则已更新，请重新生成并校对计划")
    if store.digest(payload) != draft.data["source"].get("generated_hash"):
        raise HTTPException(422, "计划只能由确定性程序生成，请更改设置后重新生成")
    end = date.fromisoformat(payload["target_date"]) + timedelta(
        days=payload["horizon_days"]
    )
    tz = ZoneInfo((await store.settings(db, owner)).data["timezone"])
    existing = await store.rows(db, owner, "plan_block")
    existing_ids = {b.id for b in existing}
    clock = now()
    today_mode = payload.get("scope") == "today"
    if today_mode and clock.astimezone(tz).date().isoformat() != payload["target_date"]:
        raise HTTPException(409, "已跨过本地午夜，请重新生成当日日程")
    removed_ids = {x["id"] for x in payload.get("removed_blocks", [])}
    selective = today_mode or payload.get("replanning") is not None
    if selective and any(
        b.id in removed_ids and instant(b.data["starts_at"]) < clock for b in existing
    ):
        raise HTTPException(409, "待替换的安排已经开始，请记录投入后重新生成")
    for b in payload["blocks"]:
        await store.owned(db, owner, b["step_id"], "step")
        if (
            b["id"] not in existing_ids
            and not b["locked"]
            and b["status"] != "completed"
            and instant(b["starts_at"]) < clock
        ):
            raise HTTPException(409, "计划的开始时间已经过去，请重新生成")
    replacing = []
    for b in existing:
        d = instant(b.data["starts_at"]).astimezone(tz).date()
        if (
            not b.data["locked"]
            and b.data["status"] != "completed"
            and (
                b.id in removed_ids
                if selective
                else (
                    date.fromisoformat(payload["target_date"]) <= d < end
                    or b.id in removed_ids
                )
            )
        ):
            replacing.append(b)
    retained = set(payload.get("changes", {}).get("retained_ids", []))
    replacing = [b for b in replacing if b.id not in retained]
    replacing_ids = {b.id for b in replacing}
    for timer in await store.rows(db, owner, "execution_timer"):
        if (
            timer.data["status"] not in ("finished", "discarded")
            and timer.data["target"].get("plan_block_id") in replacing_ids
        ):
            raise HTTPException(
                409, "待替换安排有未结束计时，请先结束或放弃计时，再重新生成计划"
            )
    # Snapshots, replacements and the draft receipt share the caller's transaction.
    await save_snapshot(db, owner, draft, payload, [store.view(b) for b in existing])
    ids = []
    for b in replacing:
        await db.delete(b)
    await db.flush()
    for b in payload["blocks"]:
        found = await db.get(Resource, b["id"])
        if found:
            if found.owner_id != owner:
                raise HTTPException(409, "计划标识冲突")
            ids.append(found.id)
            continue
        r = Resource(
            id=b["id"],
            owner_id=owner,
            kind="plan_block",
            data={k: v for k, v in b.items() if k != "id"},
        )
        db.add(r)
        ids.append(r.id)
    return ids


def planner_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/planning-capacity", response_model=CapacityReport)
    async def capacity(
        scope: Literal["range", "today"] = "range",
        target_date: date | None = None,
        horizon_days: int | None = Query(default=None, ge=1, le=7),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        fields = {"scope": scope}
        if target_date is not None:
            fields["target_date"] = target_date
        if horizon_days is not None:
            fields["horizon_days"] = horizon_days
        try:
            body = PlanRequest.model_validate(fields)
        except ValueError as exc:
            raise HTTPException(422, "当日模式不能指定其他日期或多天范围") from exc
        _, result = await planning_result(
            db, str(user.id), body.target_date, body.horizon_days, body.scope
        )
        return result["capacity"]

    from app.replanning import ReplanReport, replan_draft, replan_report

    @router.get("/replanning", response_model=ReplanReport)
    async def repair_preview(
        target_date: date | None = None,
        horizon_days: int = Query(default=7, ge=1, le=7),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        _, result = await planning_result(
            db, str(user.id), target=target_date, horizon=horizon_days, repair=True
        )
        return replan_report(result)

    @router.post("/replan-drafts", response_model=ResourceView)
    async def repair_draft(
        body: PlanRequest,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await replan_draft(db, str(user.id), body)

        return await store.mutate(
            db, str(user.id), "replan-draft", key, body.model_dump(mode="json"), op
        )

    @router.post("/plan-drafts", response_model=ResourceView)
    async def plan(
        body: PlanRequest,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            if body.expected_source_revision is not None:
                store.revision(
                    await store.settings(db, str(user.id)),
                    body.expected_source_revision,
                )
            return await generate_plan(
                db,
                str(user.id),
                body.target_date,
                body.horizon_days,
                body.scope,
                body.strategy,
            )

        return await store.mutate(
            db, str(user.id), "plan-draft", key, body.model_dump(mode="json"), op
        )

    @router.get("/plan-blocks", response_model=list[ResourceView])
    async def blocks(user=Depends(current_user), db=Depends(get_db)):
        return [store.view(b) for b in await store.rows(db, str(user.id), "plan_block")]

    @router.patch("/plan-blocks/{rid}", response_model=ResourceView)
    async def update(
        rid: str,
        body: BlockUpdate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            b = await store.owned(db, str(user.id), rid, "plan_block")
            store.revision(b, body.revision)
            data = dict(b.data)
            if body.locked is not None:
                data["locked"] = body.locked
            if body.completed is True and data["status"] != "completed":
                from app.execution import record_legacy_block_completion

                await record_legacy_block_completion(db, str(user.id), b)
                data["status"] = "completed"
            if body.completed is False and data["status"] == "completed":
                raise HTTPException(422, "已记录投入，不能直接撤销")
            b.data = data
            b.revision += 1
            await store.bump(db, str(user.id))
            return store.view(b)

        return await store.mutate(
            db,
            str(user.id),
            f"plan-block:{rid}",
            key,
            body.model_dump(exclude_unset=True),
            op,
        )

    from app.planning_options import option_router

    router.include_router(option_router(get_db, current_user))
    from app.routine_candidates import routine_router

    router.include_router(routine_router(get_db, current_user))
    return router
