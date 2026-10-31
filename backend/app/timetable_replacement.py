"""Retire removed-course actions while preserving tasks and historical records."""
from app import store


async def retire_course_links(db, owner, courses, draft_id):
    removed = {r.id: r for r in courses}
    if not removed:
        return
    for task in await store.rows(db, owner, "task"):
        course = removed.get(task.data.get("course_id"))
        if course:
            task.data = {**task.data, "course_id": None,
                         "course_snapshot": {"id": course.id, "name": course.data["name"]}}
            task.revision += 1
    for exception in await store.rows(db, owner, "exception"):
        if exception.data.get("course_id") in removed:
            exception.data = {**exception.data, "active": False,
                              "retired_by_timetable": draft_id}
            exception.revision += 1
    for draft in await store.rows(db, owner, "draft"):
        if draft.data["status"] != "pending":
            continue
        kind, payload = draft.data["draft_kind"], draft.data["payload"]
        linked = {payload.get("course_id")} if kind == "course_change" else set()
        if kind == "semester_calendar":
            linked.update(payload.get("course_ids", []))
            linked.update(c["course_id"] for c in draft.data.get("source", {}).get("preview", {}).get("changes", []))
        if linked.intersection(removed):
            draft.data = {**draft.data, "status": "superseded",
                          "invalidated_reason": "原课程已被课表覆盖，请根据新课表重新调整"}
            draft.revision += 1
    for batch in await store.rows(db, owner, "semester_calendar_batch"):
        retired = sorted({t["course_id"] for t in batch.data["targets"]}.intersection(removed))
        if retired:
            batch.data = {**batch.data, "retired_by_timetable": draft_id,
                          "retired_course_ids": retired}
            batch.revision += 1
