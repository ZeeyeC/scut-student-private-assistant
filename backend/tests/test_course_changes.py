"""Reviewed occurrence adjustments, isolated from the user's real timetable."""

from copy import deepcopy
from datetime import date, datetime

import pytest

from app import after_class, planner, schedule_reminders
from app.calendar import expand_calendar
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import confirm, resources, seed_work, write


def change(c, h, cid, action="move", **changes):
    payload = {
        "course_id": cid,
        "original_date": "2026-10-14",
        "action": action,
        "reason": "教师通知：仅本次调整",
    }
    if action == "move":
        payload.update(
            starts_at="2026-10-21T12:00:00+08:00",
            ends_at="2026-10-21T13:00:00+08:00",
            location="B202",
        )
    payload.update(changes)
    return write(c, h, "/drafts/course-change", payload)


def events(c, start="2026-10-14", end="2026-10-21"):
    return c.get(f"/api/occurrences?start={start}&end={end}").json()


def test_move_cross_week_cancel_restore_replay_original_identity_and_restart(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        courses = c.get("/api/courses").json()
        cid = courses[0]["id"]
        original = events(c)
        plan = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        d = change(c, h, cid).json()
        assert d["data"]["source"]["preview"]["timezone"] == "Asia/Shanghai"
        assert c.get("/api/course-changes").json() == [] and events(c) == original
        assert confirm(c, h, d, key="move").status_code == 200
        assert confirm(c, h, d, key="move").status_code == 200
        assert confirm(c, h, d, key="replay").status_code == 200
        # An earlier plan cannot be confirmed after a course fact changes.
        assert confirm(c, h, plan).status_code == 409
        moved = events(c)
        assert len(moved) == 1 and moved[0]["id"] == original[0]["id"]
        assert (
            moved[0]["starts_at"].startswith("2026-10-21T12:00")
            and moved[0]["location"] == "B202"
        )
        assert moved[0]["original_date"] == "2026-10-14" and moved[0]["adjusted"]
        assert events(c, "2026-10-14", "2026-10-14") == []
        cancel = change(c, h, cid, "cancel").json()
        assert cancel["data"]["source"]["preview"]["before"]["starts_at"].startswith(
            "2026-10-21"
        )
        assert confirm(c, h, cancel).status_code == 200
        assert not events(c)
        restore = change(c, h, cid, "restore").json()
        assert restore["data"]["source"]["preview"]["before"] is None
        assert confirm(c, h, restore).status_code == 200
        assert events(c) == original
        rows = c.get("/api/course-changes").json()
        assert len(rows) == 1 and rows[0]["data"]["active"] is False
        assert len(resources(c, "planning_event")) == 3
        assert len(c.get("/api/course-change-history").json()) == 3
        assert c.get("/api/courses").json() == courses
        assert not c.get("/api/plan-blocks").json()
        cookie = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert c.get("/api/course-changes").json() == rows
        assert events(c) == original
        assert len(resources(c, "planning_event")) == 3


@pytest.mark.parametrize(
    "patch",
    [
        {"original_date": "2026-10-15"},
        {"reason": "  "},
        {"starts_at": None},
        {"starts_at": "2026-10-21T12:00:00"},
        {"ends_at": "2026-10-21T11:00:00+08:00"},
        {"ends_at": "2026-10-23T12:00:00+08:00"},
        {
            "starts_at": "2028-10-21T12:00:00+08:00",
            "ends_at": "2028-10-21T13:00:00+08:00",
        },
        {"action": "cancel", "starts_at": "2026-10-21T12:00:00+08:00"},
    ],
)
def test_invalid_changes_create_no_facts(tmp_path, patch):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        cid = c.get("/api/courses").json()[0]["id"]
        assert change(c, h, cid, **patch).status_code == 422
        assert not c.get("/api/course-changes").json()
        assert not resources(c, "planning_event")


def test_preview_conflicts_locked_plans_and_changes_are_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        cid = c.get("/api/courses").json()[0]["id"]
        p = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        assert confirm(c, h, p).status_code == 200
        row = c.get("/api/plan-blocks").json()[0]
        assert (
            write(
                c,
                h,
                f"/plan-blocks/{row['id']}",
                {"revision": row["revision"], "locked": True},
                "PATCH",
            ).status_code
            == 200
        )
        fixed = write(
            c,
            h,
            "/fixed-events",
            {
                "title": "固定答辩",
                "starts_at": row["data"]["starts_at"],
                "ends_at": row["data"]["ends_at"],
            },
        ).json()
        blocks = c.get("/api/plan-blocks").json()
        d = change(
            c,
            h,
            cid,
            starts_at=row["data"]["starts_at"],
            ends_at=row["data"]["ends_at"],
        ).json()
        preview = d["data"]["source"]["preview"]
        assert {x["id"] for x in preview["conflicts"]} >= {fixed["id"], row["id"]}
        assert preview["affected_plans"][0]["locked"]
        # No retargeting a preview through generic draft editing.
        assert (
            write(
                c,
                h,
                f"/drafts/{d['id']}",
                {
                    "revision": d["revision"],
                    "payload": {**d["data"]["payload"], "original_date": "2026-10-21"},
                },
                "PUT",
            ).status_code
            == 422
        )
        from fastapi import HTTPException

        from app import course_changes

        record = course_changes.record_change

        async def failure(*args, **kwargs):
            await record(*args, **kwargs)
            raise HTTPException(503, "synthetic transaction interruption")

        with monkeypatch.context() as interrupted:
            interrupted.setattr(course_changes, "record_change", failure)
            assert confirm(c, h, d, key="recover").status_code == 503
        assert not c.get("/api/course-changes").json()
        assert c.get("/api/plan-blocks").json() == blocks
        assert confirm(c, h, d, key="recover").status_code == 200
        assert c.get("/api/plan-blocks").json() == blocks
        # The planner reads the moved course as a hard busy fact.
        new = write(c, h, "/plan-drafts", {"scope": "today"}).json()["data"]["payload"]
        assert any("冲突" in w for w in new["warnings"])
        assert (
            not new["changes"]["removed_ids"]
            or row["id"] not in new["changes"]["removed_ids"]
        )


def test_stale_draft_owner_and_cancelled_draft_cannot_write(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        cid = c.get("/api/courses").json()[0]["id"]
        d = change(c, h, cid).json()
        cancel = change(c, h, cid, "cancel").json()
        assert confirm(c, h, cancel).status_code == 200
        assert confirm(c, h, d).status_code == 409
        restore = change(c, h, cid, "restore").json()
        assert (
            write(
                c,
                h,
                f"/drafts/{restore['id']}",
                {"revision": restore["revision"]},
                "DELETE",
            ).status_code
            == 200
        )
        assert confirm(c, h, restore).status_code == 409
        c.post("/api/auth/logout", headers=h)
        other = register_login(c, "other@example.com")
        assert not c.get("/api/course-changes").json()
        assert not c.get("/api/course-change-history").json()
        assert change(c, other, cid).status_code == 404
        assert confirm(c, other, d).status_code == 404


def test_multiple_courses_same_day_and_legacy_duplicates_are_reversible(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        courses = c.get("/api/courses").json()
        cid = courses[0]["id"]
        # Older APIs could leave several records for one original occurrence.
        for i in [0, 1]:
            response = write(
                c,
                h,
                "/calendar-exceptions",
                {"course_id": cid, "date": "2026-10-14", "cancelled": True},
                key=f"legacy-{i}",
            )
            assert response.status_code == 200
        other = deepcopy(courses[0]["data"])
        other.update(source_key="another", name="另一门课")
        d = write(
            c, h, "/drafts/timetable", {"semester_label": "合成", "courses": [other]}
        ).json()
        assert confirm(c, h, d).status_code == 200
        original_other = events(c)
        assert len(original_other) == 1 and original_other[0]["title"] == "另一门课"
        d = change(c, h, cid, "restore").json()
        assert confirm(c, h, d).status_code == 200
        assert len(events(c)) == 2
        assert all(
            not r["data"].get("active", True)
            for r in c.get("/api/course-changes").json()
        )
        # Reapplying one reviewed adjustment reuses the canonical resource ID.
        d = change(c, h, cid).json()
        assert confirm(c, h, d).status_code == 200
        assert (
            sum(
                r["data"].get("active", True)
                for r in c.get("/api/course-changes").json()
            )
            == 1
        )
        assert (
            next(e for e in events(c) if e["title"] == "另一门课") == original_other[0]
        )


def test_reminder_and_after_class_use_effective_course_times(tmp_path, monkeypatch):
    clock = [datetime.fromisoformat("2026-10-14T08:57:00+08:00")]
    monkeypatch.setattr(schedule_reminders, "now", lambda: clock[0])
    monkeypatch.setattr(
        after_class, "now", lambda: datetime.fromisoformat("2026-10-14T10:31:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        cid = c.get("/api/courses").json()[0]["id"]
        assert len(c.get("/api/schedule-reminders").json()) == 1
        moved = change(
            c,
            h,
            cid,
            starts_at="2026-10-14T11:00:00+08:00",
            ends_at="2026-10-14T12:00:00+08:00",
        ).json()
        assert confirm(c, h, moved).status_code == 200
        assert not c.get("/api/schedule-reminders").json()
        clock[0] = datetime.fromisoformat("2026-10-14T10:57:00+08:00")
        assert len(c.get("/api/schedule-reminders").json()) == 1
        d = change(c, h, cid, "cancel").json()
        assert confirm(c, h, d).status_code == 200
        agenda = c.get("/api/calendar-events?start=2026-10-14&end=2026-10-14").json()
        assert not any(e["kind"] == "course" for e in agenda["events"])
        assert not c.get("/api/schedule-reminders").json()
        # Existing after-class reader no longer infers a class on the cancelled date.
        response = write(c, h, "/after-class/open", {})
        assert response.status_code == 200, response.text
        assert response.json()["due"] is False
        assert response.json()["reason"] == "这一天没有课程"


def test_inactive_exception_does_not_mask_active_legacy_or_change_course_week_rules():
    settings = {
        "timezone": "Asia/Shanghai",
        "week1_monday": "2026-10-12",
        "week_count": 3,
        "periods": {"1": {"start": "09:00", "end": "10:00"}},
    }
    courses = [
        {
            "id": "c",
            "data": {"name": "数学", "weeks": [1, 3], "weekday": 3, "periods": [1]},
        }
    ]
    inactive = {
        "course_id": "c",
        "date": "2026-10-14",
        "active": False,
        "cancelled": True,
    }
    got = expand_calendar(
        settings, courses, [inactive], date(2026, 10, 12), date(2026, 11, 1)
    )
    assert [e["original_date"] for e in got] == ["2026-10-14", "2026-10-28"]
    got = expand_calendar(
        settings,
        courses,
        [{**inactive, "active": True}, inactive],
        date(2026, 10, 12),
        date(2026, 11, 1),
    )
    assert len(got) == 1


def test_explicit_empty_location_and_midnight_move_match_preview(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        cid = c.get("/api/courses").json()[0]["id"]
        d = change(
            c,
            h,
            cid,
            starts_at="2026-10-20T23:30:00+08:00",
            ends_at="2026-10-21T00:30:00+08:00",
            location="",
        ).json()
        assert confirm(c, h, d).status_code == 200
        event = events(c, "2026-10-20", "2026-10-20")[0]
        assert events(c, "2026-10-21", "2026-10-21")[0] == event
        assert event["location"] == ""
        assert (
            event["starts_at"] == d["data"]["source"]["preview"]["after"]["starts_at"]
        )
        rows = c.get("/api/course-change-history").json()
        assert (
            rows[0]["data"]["details"]["after"]["data"]["source"]["reason"]
            == d["data"]["payload"]["reason"]
        )


def test_overnight_move_blocks_next_days_remaining_time(tmp_path, monkeypatch):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T00:10:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        s = c.get("/api/settings").json()
        s["data"]["study_windows"] = [{"start": "00:00", "end": "03:00"}]
        assert write(c, h, "/settings", s, "PUT").status_code == 200
        cid = c.get("/api/courses").json()[0]["id"]
        d = change(
            c,
            h,
            cid,
            starts_at="2026-10-13T23:30:00+08:00",
            ends_at="2026-10-14T01:00:00+08:00",
        ).json()
        assert confirm(c, h, d).status_code == 200
        plan = write(c, h, "/plan-drafts", {"scope": "today"}).json()["data"]["payload"]
        assert plan["fixed_agenda"]
        assert plan["blocks"]
        assert all(
            datetime.fromisoformat(b["starts_at"])
            >= datetime.fromisoformat("2026-10-14T01:10:00+08:00")
            for b in plan["blocks"]
        )
