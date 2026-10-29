"""Read persisted courses, fixed events and plan blocks in one user timezone."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import store
from app.calendar import expand_calendar, occupied_course_events
from app.constraints import expand_constraints
from app.conflicts import detect_conflicts


async def calendar_events(db, owner, start, end):
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "日期范围应在一年内")
    settings = await store.settings(db, owner)
    tz = ZoneInfo(settings.data["timezone"])
    lower = datetime.combine(start, time.min, tz)
    upper = datetime.combine(end + timedelta(days=1), time.min, tz)
    warnings = []
    try:
        courses = expand_calendar(
            settings.data,
            [store.view(r) for r in await store.rows(db, owner, "course")],
            [r.data for r in await store.rows(db, owner, "exception")],
            start,
            end,
        )
    except ValueError as exc:
        courses = []
        warnings.append(str(exc))
    # Envelopes can contain free, nonconsecutive periods. Only occupied runs
    # become actual calendar events, including their explicitly protected breaks.
    events = [{**event, "kind": "course"} for event in occupied_course_events(courses)]
    tasks = {r.id: r.data["title"] for r in await store.rows(db, owner, "task")}
    for kind in ["fixed_event", "plan_block"]:
        for row in await store.rows(db, owner, kind):
            data = row.data
            a, b = (
                datetime.fromisoformat(data["starts_at"]),
                datetime.fromisoformat(data["ends_at"]),
            )
            if a < upper and b > lower:
                events.append(
                    {
                        "id": row.id,
                        "kind": kind,
                        "title": data.get("title")
                        or tasks.get(data.get("task_id"), "学习安排"),
                        "starts_at": data["starts_at"],
                        "ends_at": data["ends_at"],
                        "location": data.get("location"),
                        "locked": data.get("locked", False),
                    }
                )
    try:
        constraints = expand_constraints([store.view(r) for r in await store.rows(db, owner, "scheduling_constraint") if r.data.get("strength", "hard") == "hard"], lower, upper)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    for row in constraints:
        data = row["data"]
        a, b = datetime.fromisoformat(data["starts_at"]), datetime.fromisoformat(data["ends_at"])
        if a < upper and b > lower:
            events.append({"id": row["id"], "kind": "scheduling_constraint", "title": data["title"], "starts_at": data["starts_at"], "ends_at": data["ends_at"], "constraint_id": row.get("constraint_id", row["id"]), "recurrence": data.get("recurrence", "once")})
    return {
        "events": sorted(
            events, key=lambda x: (datetime.fromisoformat(x["starts_at"]), x["id"])
        ),
        "warnings": warnings,
        "conflict_report": detect_conflicts(events, settings.data),
    }
