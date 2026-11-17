"""Authoritative lesson references shared by homework entry and agent tools."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import store
from app.calendar import expand_calendar
from app.db import Resource


def occurrence_snapshot(event, timezone):
    return {
        "id": event["id"],
        "course_id": event["course_id"],
        "original_date": event["original_date"],
        "name": event["title"],
        "starts_at": event["starts_at"],
        "ends_at": event["ends_at"],
        "timezone": timezone,
        "fingerprint": store.digest(event),
    }


async def resolve_occurrence(db, owner, reference):
    course = await store.owned(db, owner, reference["course_id"], "course")
    settings = await store.settings(db, owner)
    original = date.fromisoformat(reference["original_date"])
    exceptions = [r.data for r in await store.rows(db, owner, "exception")]
    actual = original
    for item in exceptions:
        if (item.get("active", True) and item["course_id"] == course.id
                and item["date"] == original.isoformat()):
            actual = (datetime.fromisoformat(item["starts_at"]).astimezone(
                ZoneInfo(settings.data["timezone"])).date()
                if item.get("starts_at") else original)
    try:
        events = expand_calendar(settings.data, [store.view(course)], exceptions, actual, actual)
    except ValueError as exc:
        raise HTTPException(409, "课程发生已变化，请重新选择课程") from exc
    event = next((e for e in events if e["id"] == f"{course.id}:{original}"), None)
    if event is None:
        raise HTTPException(409, "这次课程已取消或不存在，请重新选择课程")
    return occurrence_snapshot(event, settings.data["timezone"])


async def assignment_snapshots(db, owner, payload):
    snapshots = []
    for item in payload["items"]:
        reference = item.get("course_occurrence")
        snapshot = None
        if reference:
            if item.get("course_id") not in (None, reference["course_id"]):
                raise HTTPException(422, "关联课程与所选课次不一致")
            snapshot = await resolve_occurrence(db, owner, reference)
            item["course_id"] = reference["course_id"]
        snapshots.append(snapshot)
    return snapshots


async def recorded_occurrences(db, owner):
    ids = set()
    for task in await store.rows(db, owner, "task"):
        data = task.data
        for snapshot in data.get("course_occurrences", []):
            ids.add(snapshot["id"])
        reference = data.get("course_occurrence")
        if reference:
            ids.add(f"{reference['course_id']}:{reference['original_date']}")
    return ids


async def invalidate_open_review(db, owner, snapshot):
    from app.after_class import review_id

    day = datetime.fromisoformat(snapshot["starts_at"]).astimezone(
        ZoneInfo(snapshot["timezone"])).date()
    review = await db.get(Resource, review_id(owner, day))
    if review is not None and review.owner_id == owner:
        review.revision += 1
