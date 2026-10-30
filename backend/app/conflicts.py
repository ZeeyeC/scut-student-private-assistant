"""One deterministic check for occupied course runs and confirmed fixed facts.

Campus names and directional travel minutes are user facts, never inferred from
rooms or invented by a model. Missing information remains an explicit question.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import store
from app.calendar import expand_calendar, occupied_course_events

REVIEW_KINDS = {
    "timetable",
    "timetable_recognition",
    "timetable_text",
    "calendar_event",
    "course_change",
    "semester_calendar",
}
CONFLICT_VERSION = "course-conflicts-1"


def instant(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def detect_conflicts(events, settings, focus=None):
    """Half-open actual occupied intervals; canonical envelopes are not used."""
    items = sorted(
        (
            e
            for e in occupied_course_events(events)
            if e.get("kind", "course") in {"course", "fixed_event"}
        ),
        key=lambda e: (instant(e["starts_at"]), instant(e["ends_at"]), e["id"]),
    )
    issues = []
    tz = ZoneInfo(settings["timezone"])
    rules = {
        (r["from_campus"], r["to_campus"]): r["minutes"]
        for r in settings.get("campus_transfers", [])
    }

    def add(code, a, b, message, **details):
        if focus is not None and not (
            {a.get("course_id", a["id"]), b.get("course_id", b["id"])} & focus
        ):
            return
        issues.append(
            {
                "id": store.digest([CONFLICT_VERSION, code, a["id"], b["id"]]),
                "code": code,
                "severity": "pending" if code.startswith("unknown_") else "conflict",
                "message": message,
                "first": a,
                "second": b,
                **details,
            }
        )

    # Sweep the active intervals. Test all overlaps, including a long fixed event
    # enclosing several courses, and retain distinct occupied runs as evidence.
    active = []
    for event in items:
        start = instant(event["starts_at"])
        active = [a for a in active if instant(a["ends_at"]) > start]
        for other in active:
            if other.get("occurrence_id", other["id"]) == event.get(
                "occurrence_id", event["id"]
            ):
                continue
            add(
                "overlap",
                other,
                event,
                f"“{other['title']}”与“{event['title']}”时间重叠",
                overlap_starts_at=max(instant(other["starts_at"]), start).isoformat(),
                overlap_ends_at=min(
                    instant(other["ends_at"]), instant(event["ends_at"])
                ).isoformat(),
            )
        active.append(event)

    # A transfer is meaningful only between successive, non-overlapping courses
    # on the same local day. An overlapping cluster has no unambiguous departure
    # course, so its outgoing transfer stays pending until the overlap is fixed.
    courses = [e for e in items if e.get("kind", "course") == "course"]
    previous = None
    ambiguous = False
    for event in courses:
        if previous is None:
            previous = event
            continue
        start, end = instant(event["starts_at"]), instant(previous["ends_at"])
        if start < end:
            ambiguous = True
            if instant(event["ends_at"]) > end:
                previous = event
            continue
        same_day = start.astimezone(tz).date() == end.astimezone(tz).date()
        same_occurrence = previous.get("occurrence_id", previous["id"]) == event.get(
            "occurrence_id", event["id"]
        )
        if same_day and not same_occurrence:
            available = (start - end).total_seconds() / 60
            a, b = (
                (previous.get("campus") or "").strip(),
                (event.get("campus") or "").strip(),
            )
            if ambiguous:
                add(
                    "unknown_departure",
                    previous,
                    event,
                    "前序课程存在重叠，请先核对课程，再检查跨校区转移",
                )
            elif not a or not b:
                add(
                    "unknown_campus",
                    previous,
                    event,
                    "请补充这两门课程的校区，暂不能判断能否赶上",
                    available_minutes=available,
                )
            elif a != b:
                required = rules.get((a, b))
                if required is None:
                    add(
                        "unknown_transfer",
                        previous,
                        event,
                        f"请确认 {a} → {b} 需要多少分钟，暂不能判断能否赶上",
                        from_campus=a,
                        to_campus=b,
                        available_minutes=available,
                    )
                elif available < required:
                    add(
                        "transfer_shortfall",
                        previous,
                        event,
                        f"{a} → {b} 需 {required} 分钟，实际间隔 {available:g} 分钟，不足 {required - available:g} 分钟",
                        from_campus=a,
                        to_campus=b,
                        required_minutes=required,
                        available_minutes=available,
                        shortfall_minutes=required - available,
                        basis="user_confirmed",
                    )
        previous, ambiguous = event, False
    return {
        "rule_version": CONFLICT_VERSION,
        "issues": issues,
        "conflict_count": sum(i["severity"] == "conflict" for i in issues),
        "pending_count": sum(i["severity"] == "pending" for i in issues),
    }


async def draft_conflicts(db, owner, draft, payload):
    """Simulate the exact save semantics without writing courses or exceptions."""
    from app.imports import validate_payload

    kind = draft.data["draft_kind"]
    if kind not in REVIEW_KINDS or draft.data["status"] != "pending":
        raise HTTPException(409, "请选择尚未保存的课表、固定事项或课程调整草稿")
    payload = validate_payload(kind, payload)
    if kind == "semester_calendar":
        from app.semester_calendar import preview_semester

        if payload != draft.data["payload"]:
            raise HTTPException(422, "校历规则与原预览绑定，请重新生成草稿")
        preview = await preview_semester(db, owner, payload)
        return {
            **preview["conflict_report"],
            "complete": True,
            "configuration_warnings": [],
            "timezone": preview["timezone"],
            "conflict_token": store.digest(
                [owner, draft.id, CONFLICT_VERSION, payload, preview["versions"]]
            ),
            "message": "仅检查本批实际课程。校区和转移时间以确认信息为准，已有计划不会自动移动。",
        }
    s = await store.settings(db, owner)
    courses = [store.view(r) for r in await store.rows(db, owner, "course")]
    exceptions = await store.rows(db, owner, "exception")
    fixed = await store.rows(db, owner, "fixed_event")
    versions = {
        "settings": s.revision,
        "courses": [(r["id"], r["revision"]) for r in courses],
        "exceptions": [(r.id, r.revision) for r in exceptions],
        "fixed": [(r.id, r.revision) for r in fixed],
    }
    touched = set()
    replacement = None
    if kind == "timetable":
        existing = {r["data"]["source_key"]: r for r in courses}
        for c in payload["courses"]:
            old = existing.get(c["source_key"])
            rid = old["id"] if old else "candidate:" + c["source_key"]
            courses = [r for r in courses if r["id"] != rid]
            courses.append({"id": rid, "data": c})
            touched.add(rid)
        if payload["completeness"] == "full" and draft.data.get("source", {}).get(
            "verified_full"
        ):
            keys = {c["source_key"] for c in payload["courses"]}
            courses = [r for r in courses if r["data"]["source_key"] in keys]
    elif kind in {"timetable_recognition", "timetable_text"}:
        from app.timetable_recognition import reviewed_courses, validate_review_edit

        validate_review_edit(draft.data["payload"], payload)
        candidates = reviewed_courses(
            payload,
            s.data,
            draft.id if kind == "timetable_text" else draft.data["source"]["asset_id"],
            "text" if kind == "timetable_text" else "ocr",
        )
        fields = (
            "name",
            "teacher",
            "campus",
            "location",
            "weekday",
            "weeks",
            "periods",
        )

        def facts(c):
            return store.digest({k: c.get(k) or None for k in fields})

        known = {facts(r["data"]): r["id"] for r in courses}
        for c in candidates:
            key = facts(c)
            if key not in known:
                known[key] = "candidate:" + c["source_key"]
                courses.append({"id": known[key], "data": c})
            touched.add(known[key])
    elif kind == "course_change":
        from app.course_changes import preview

        if payload != draft.data["payload"]:
            raise HTTPException(422, "课程调整与原预览绑定，请重新生成草稿")
        review = await preview(db, owner, payload)
        replacement = (review["original"]["id"], review["after"])
        touched.add(payload["course_id"])
    else:
        touched.add("candidate:fixed")

    # Include explicit moved occurrences outside the teaching semester as well.
    anchor = (
        date.fromisoformat(s.data["week1_monday"])
        if s.data.get("week1_monday")
        else date.today()
    )
    days = [anchor, anchor + timedelta(weeks=s.data["week_count"], days=-1)]
    tz = ZoneInfo(s.data["timezone"])
    for e in (
        [r.data for r in exceptions]
        + ([payload] if kind == "calendar_event" else [])
        + ([replacement[1]] if replacement and replacement[1] else [])
    ):
        for field in ("starts_at", "ends_at"):
            if e.get(field):
                days.append(datetime.fromisoformat(e[field]).astimezone(tz).date())
    configuration_warnings = []
    try:
        events = expand_calendar(
            s.data, courses, [r.data for r in exceptions], min(days), max(days)
        )
    except ValueError as exc:
        events = []
        configuration_warnings.append("课程冲突尚不能完整检查：" + str(exc))
    if replacement:
        events = [e for e in events if e["id"] != replacement[0]]
        if replacement[1]:
            events.append(replacement[1])
    events = [{**e, "kind": "course"} for e in occupied_course_events(events)]
    events.extend({"id": r.id, "kind": "fixed_event", **r.data} for r in fixed)
    if kind == "calendar_event":
        events.append({"id": "candidate:fixed", "kind": "fixed_event", **payload})
    report = detect_conflicts(events, s.data, touched)
    return {
        **report,
        "complete": not configuration_warnings,
        "configuration_warnings": configuration_warnings,
        "pending_count": report["pending_count"] + len(configuration_warnings),
        "timezone": s.data["timezone"],
        "conflict_token": store.digest(
            [owner, draft.id, CONFLICT_VERSION, payload, versions]
        ),
        "message": "检查实际授课及受保护课间与固定事项。校区和转移时间以你确认的信息为准；固定课程不会自动移动。",
    }
