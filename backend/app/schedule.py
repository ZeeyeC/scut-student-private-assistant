"""Read persisted courses, fixed events and plan blocks in one user timezone."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import store
from app.calendar import expand_calendar


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
    events = [{**event, "kind": "course"} for event in courses]
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
    return {
        "events": sorted(
            events, key=lambda x: (datetime.fromisoformat(x["starts_at"]), x["id"])
        ),
        "warnings": warnings,
    }
