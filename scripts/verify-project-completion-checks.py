"""Run the new domain checks against the actual frozen service, without models."""

from datetime import timedelta


def checks(get, write, task_id, local_day):
    before = get("/plan-blocks")
    task = get(f"/tasks/{task_id}")
    payload = {
        "revision": 0,
        "target_revision": task["revision"],
        "task_type": "deep",
        "difficulty": "high",
    }
    saved = write(
        f"/study-types/task/{task_id}", payload, method="PUT", key="completion-type"
    )
    assert (
        write(
            f"/study-types/task/{task_id}", payload, method="PUT", key="completion-type"
        )
        == saved
    )
    assert get(f"/tasks/{task_id}") == task
    assert any(
        i["classification"] and i["classification"]["data"]["task_type"] == "deep"
        for i in get("/study-types")["items"]
    )
    target = local_day + timedelta(days=1)
    settings = get("/settings")
    settings["data"].update(
        week1_monday=str(target - timedelta(days=target.weekday())),
        week_count=2,
        periods={
            "1": {"start": "09:00", "end": "10:00"},
            "3": {"start": "14:00", "end": "15:00"},
        },
    )
    write("/settings", settings, method="PUT")
    d = write(
        "/drafts/timetable",
        {
            "semester_label": "冻结校历合成验收",
            "courses": [
                {
                    "source_key": "completion-course",
                    "name": "冻结分段实验",
                    "weekday": target.isoweekday(),
                    "weeks": [1],
                    "periods": [1, 3],
                    "campus": "主校区",
                    "location": "101",
                }
            ],
        },
    )
    cid = write(f"/drafts/{d['id']}/confirm", {"revision": d["revision"]})["saved_ids"][
        0
    ]
    course = next(c for c in get("/courses") if c["id"] == cid)
    write(
        f"/study-types/course/{cid}",
        {"revision": 0, "target_revision": course["revision"], "course_type": "lab"},
        method="PUT",
    )
    routine = write(
        "/daily-routine-preview",
        {
            "confirmed": True,
            "target_date": str(target),
            "horizon_days": 1,
            "course_type_rules": [{"course_type": "lab", "preparation_minutes": 20}],
        },
    )
    prep = next(
        c for c in routine["candidates"] if c["basis"].get("course_type") == "lab"
    )
    assert prep["basis"]["minutes"] == 20
    moved = target + timedelta(days=1)
    payload = {
        "operation": "apply",
        "rule_kind": "makeup",
        "title": "冻结明确补课",
        "reason": "隔离合成通知",
        "source_scope": "仅此课程原日",
        "course_ids": [cid],
        "action": "move",
        "mappings": [{"original_date": str(target), "target_date": str(moved)}],
    }
    d = write("/drafts/semester-calendar", payload, key="completion-batch")
    assert write("/drafts/semester-calendar", payload, key="completion-batch") == d
    report = write(
        f"/drafts/{d['id']}/conflict-preview",
        {"revision": d["revision"], "payload": d["data"]["payload"]},
    )
    write(
        f"/drafts/{d['id']}/confirm",
        {"revision": d["revision"], "conflict_token": report["conflict_token"]},
    )
    occurrence = next(
        e
        for e in get(f"/occurrences?start={moved}&end={moved}")
        if e["course_id"] == cid
    )
    assert len(occurrence["occupied_intervals"]) == 2 and occurrence[
        "original_date"
    ] == str(target)
    batch = next(
        b for b in get("/semester-calendars") if b["data"]["draft_id"] == d["id"]
    )
    undo = write(
        "/drafts/semester-calendar",
        {"operation": "undo", "batch_id": batch["id"], "reason": "合成撤销验收"},
    )
    write(f"/drafts/{undo['id']}/confirm", {"revision": undo["revision"]})
    assert any(
        e["course_id"] == cid for e in get(f"/occurrences?start={target}&end={target}")
    )
    assert get("/plan-blocks") == before
    return [
        "explicit-types-persist-with-exact-receipt",
        "types-preserve-authoritative-task-facts",
        "confirmed-lab-rule-preview-only",
        "semester-batch-original-draft-confirm",
        "makeup-preserves-nonconsecutive-periods",
        "semester-undo-restores-original-date",
        "batch-and-types-preserve-existing-plan",
    ]
