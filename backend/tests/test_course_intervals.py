"""A1: synthetic interval/real SQLite scenarios, never personal timetables."""

from copy import deepcopy
from datetime import date

import pytest

from app import after_class, planner, schedule_reminders
from app.calendar import course_intervals, expand_calendar, occupied_course_events
from app.planner import build_plan, instant
from tests.test_course_changes import change
from tests.test_foundation import make_client, register_login
from tests.test_planner import fixture
from tests.test_scheduling_constraints import confirm, seed_work, write

DAY = date(2026, 10, 14)
WINDOWS = {
    "1": {"start": "09:00", "end": "09:40"},
    "2": {"start": "10:00", "end": "10:40"},
    "3": {"start": "11:00", "end": "11:40"},
}


def spec(periods=(1, 3)):
    settings = {
        "timezone": "Asia/Shanghai",
        "week1_monday": "2026-10-12",
        "week_count": 20,
        "periods": deepcopy(WINDOWS),
    }
    courses = [
        {
            "id": "math",
            "data": {
                "name": "高数",
                "weekday": 3,
                "weeks": [1, 2],
                "periods": list(periods),
            },
        }
    ]
    return settings, courses


def expand(periods=(1, 3), exceptions=()):
    s, courses = spec(periods)
    return expand_calendar(s, courses, list(exceptions), DAY, DAY)[0]


def test_numerically_nonconsecutive_periods_do_not_occupy_the_gap_and_ids_are_stable():
    event = expand((3, 1, 1))
    assert event["id"] == "math:2026-10-14"
    assert [part["periods"] for part in event["teaching_intervals"]] == [[1], [3]]
    assert event["break_intervals"] == []
    runs = occupied_course_events([event])
    assert occupied_course_events(runs) == runs
    assert [part["periods"] for part in runs] == [[1], [3]]
    assert [part["id"] for part in runs] == [event["id"], event["id"] + ":period-3"]
    assert all(part["occurrence_id"] == event["id"] for part in runs)
    assert runs[0]["ends_at"].endswith("09:40:00+08:00")
    assert runs[1]["starts_at"].endswith("11:00:00+08:00")
    assert occupied_course_events([expand((1, 3))]) == runs


def test_adjacent_period_breaks_are_recorded_separately_and_protected():
    event = expand((1, 2, 3))
    assert len(event["teaching_intervals"]) == 3
    assert len(event["break_intervals"]) == 2
    assert all(part["protected"] for part in event["break_intervals"])
    assert len(event["occupied_intervals"]) == 1
    assert event["break_intervals"][0]["starts_at"].endswith("09:40:00+08:00")
    assert event["break_intervals"][0]["ends_at"].endswith("10:00:00+08:00")


def test_touching_periods_have_no_fictional_break():
    s, courses = spec((1, 2))
    s["periods"]["2"]["start"] = "09:40"
    event = expand_calendar(s, courses, [], DAY, DAY)[0]
    assert not event["break_intervals"] and len(event["occupied_intervals"]) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"2": None},
        {"2": {"start": "09:30", "end": "10:40"}},
        {"2": {"start": "10:00", "end": "10:00"}},
        {"2": {"start": "10:00+08:00", "end": "10:40+08:00"}},
    ],
)
def test_missing_overlapping_or_invalid_period_mapping_is_not_guessed(patch):
    s, courses = spec((1, 2))
    s["periods"].update(patch)
    with pytest.raises(ValueError):
        course_intervals(s, courses[0]["data"], DAY)


def test_planning_uses_the_free_gap_and_preserved_blocks_are_not_false_conflicts():
    p = fixture()
    p["now_utc"] = instant("2026-10-14T08:00:00+08:00")
    p["occurrences"] = [expand()]
    p["settings"]["study_windows"] = [{"start": "09:00", "end": "12:00"}]
    result = build_plan(p)
    assert len(result["fixed_agenda"]) == 2
    assert any(
        instant(b["starts_at"]) == instant("2026-10-14T09:50:00+08:00")
        and instant(b["ends_at"]) == instant("2026-10-14T10:50:00+08:00")
        for b in result["blocks"]
    )
    p["preserved_blocks"] = [
        {
            "id": "kept-gap",
            "step_id": "a",
            "task_id": "t1",
            "title": "空档学习",
            "starts_at": "2026-10-14T10:00:00+08:00",
            "ends_at": "2026-10-14T10:30:00+08:00",
            "locked": True,
            "status": "suggested",
        }
    ]
    result = build_plan(p)
    assert p["preserved_blocks"][0] in result["blocks"]
    assert not result["warnings"]
    p["preserved_blocks"][0].update(
        starts_at="2026-10-14T09:10:00+08:00", ends_at="2026-10-14T09:30:00+08:00"
    )
    assert build_plan(p)["warnings"]


def test_even_a_long_adjacent_break_is_protected_and_not_filled_by_short_tasks():
    p = fixture()
    p["now_utc"] = instant("2026-10-14T08:00:00+08:00")
    p["settings"].update(
        buffer_minutes=0,
        min_block_minutes=5,
        study_windows=[{"start": "09:40", "end": "10:00"}],
    )
    p["occurrences"] = [expand((1, 2))]
    assert not build_plan(p)["blocks"]
    p["occurrences"] = [expand((1, 3))]
    assert build_plan(p)["blocks"]


def test_room_only_preserves_segments_explicit_move_does_not_invent_new_breaks():
    s, courses = spec()
    original = expand()
    ex = {
        "course_id": "math",
        "date": DAY.isoformat(),
        "starts_at": original["starts_at"],
        "ends_at": original["ends_at"],
        "location": "B202",
    }
    room = expand_calendar(s, courses, [ex], DAY, DAY)[0]
    assert room["occupied_intervals"] == original["occupied_intervals"]
    moved = expand_calendar(
        s,
        courses,
        [
            {
                **ex,
                "starts_at": "2026-10-15T23:30:00+08:00",
                "ends_at": "2026-10-16T00:30:00+08:00",
            }
        ],
        date(2026, 10, 16),
        date(2026, 10, 16),
    )[0]
    assert moved["id"] == original["id"] and len(moved["occupied_intervals"]) == 1
    assert (
        moved["break_intervals"] == []
        and moved["teaching_intervals"][0]["periods"] == []
    )
    assert expand_calendar(s, courses, [{**ex, "active": False}], DAY, DAY) == [
        original
    ]


def seed_split(c, h, periods=(1, 3)):
    seed_work(c, h)
    s = c.get("/api/settings").json()
    s["data"].update(periods=deepcopy(WINDOWS), buffer_minutes=0)
    assert write(c, h, "/settings", s, "PUT").status_code == 200
    course = c.get("/api/courses").json()[0]
    course["data"]["periods"] = list(periods)
    d = write(
        c,
        h,
        "/drafts/timetable",
        {"semester_label": "合成", "courses": [course["data"]]},
    ).json()
    assert confirm(c, h, d).status_code == 200
    return course["id"]


def test_sqlite_calendar_preview_room_change_cancel_restore_and_restart(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        cid = seed_split(c, h)
        url = "/api/calendar-events?start=2026-10-14&end=2026-10-14"
        original = c.get(url).json()["events"]
        assert len(original) == 2
        fixed = write(
            c,
            h,
            "/fixed-events",
            {
                "title": "未上课节次中的事项",
                "starts_at": "2026-10-14T10:00:00+08:00",
                "ends_at": "2026-10-14T10:30:00+08:00",
            },
        ).json()
        d = change(
            c,
            h,
            cid,
            starts_at="2026-10-14T09:00:00+08:00",
            ends_at="2026-10-14T11:40:00+08:00",
        ).json()
        review = d["data"]["source"]["preview"]
        assert not review["conflicts"] and not review["affected_plans"]
        assert (
            len(review["before"]["occupied_intervals"])
            == len(review["after"]["occupied_intervals"])
            == 2
        )
        assert confirm(c, h, d).status_code == 200
        actual = [e for e in c.get(url).json()["events"] if e["kind"] == "course"]
        assert [e["id"] for e in actual] == [e["id"] for e in original]
        assert all(e["location"] == "B202" for e in actual)
        assert confirm(c, h, change(c, h, cid, "cancel").json()).status_code == 200
        assert [e["id"] for e in c.get(url).json()["events"]] == [fixed["id"]]
        d = change(c, h, cid, "restore").json()
        assert not d["data"]["source"]["preview"]["conflicts"]
        assert confirm(c, h, d).status_code == 200
        assert [
            e for e in c.get(url).json()["events"] if e["kind"] == "course"
        ] == original
        cookies = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        assert [
            e for e in c.get(url).json()["events"] if e["kind"] == "course"
        ] == original


def test_reminders_per_occupied_run_not_break_and_after_class_waits_for_last_period(
    tmp_path, monkeypatch
):
    clock = [instant("2026-10-14T08:57:00+08:00")]
    monkeypatch.setattr(schedule_reminders, "now", lambda: clock[0])
    monkeypatch.setattr(after_class, "now", lambda: clock[0])
    with make_client(tmp_path) as c:
        h = register_login(c)
        cid = seed_split(c, h)
        first = c.get("/api/schedule-reminders").json()
        assert len(first) == 1 and first[0]["id"] == f"{cid}:2026-10-14"
        clock[0] = instant("2026-10-14T10:57:00+08:00")
        last = c.get("/api/schedule-reminders").json()
        assert len(last) == 1 and last[0]["id"] == f"{cid}:2026-10-14:period-3"
        assert first[0]["key"] != last[0]["key"]
        assert write(c, h, "/after-class/open", {}).json()["due"] is False
        clock[0] = instant("2026-10-14T12:11:00+08:00")
        result = write(c, h, "/after-class/open", {}).json()
        assert result["due"] and len(result["courses"]) == 1
    with make_client(tmp_path / "adjacent") as c:
        h = register_login(c)
        seed_split(c, h, periods=(1, 2))
        clock[0] = instant("2026-10-14T09:57:00+08:00")
        assert not c.get("/api/schedule-reminders").json()


@pytest.mark.parametrize("source", ["image", "text"])
def test_reviewed_image_and_text_can_save_nonconsecutive_mapped_periods(
    tmp_path, source
):
    from tests.test_assignments import png
    from tests.test_timetable_recognition import (
        FakeTimetableVision,
        candidate,
        edit,
        recognize,
        reviewed,
        settings,
        upload,
    )
    from tests.test_timetable_text import create

    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        s = c.get("/api/settings").json()
        s["data"]["periods"]["3"] = {"start": "10:00", "end": "10:45"}
        assert write(c, h, "/settings", s, "PUT").status_code == 200
        if source == "image":
            c.app.state.gateway = FakeTimetableVision([candidate(periods=[1, 3])])
            job = recognize(c, h, upload(c, h, raw=png()))
            d = c.get("/api/drafts/" + job["data"]["draft_id"]).json()
        else:
            d, _, _ = create(c, h, periods=[1, 3])
            assert not d["data"]["clarifications"]
        d = edit(c, h, d, reviewed(d))
        assert confirm(c, h, d).status_code == 200
        events = c.get("/api/calendar-events?start=2026-09-07&end=2026-09-07").json()[
            "events"
        ]
        assert len(events) == 2 and all(e["periods"] in ([1], [3]) for e in events)


def test_rule_upgrade_rejects_pending_old_plan_and_course_adjustment_without_writes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(planner, "now", lambda: instant("2026-10-14T08:00:00+08:00"))
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        with monkeypatch.context() as old:
            old.setattr(planner, "PLANNER_RULE_VERSION", "today-1")
            draft = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        assert confirm(c, h, draft).status_code == 409
        assert not c.get("/api/plan-blocks").json()
        cid = c.get("/api/courses").json()[0]["id"]
        from app import course_changes

        real_expand = course_changes.expand_calendar

        def legacy_expand(*args, **kwargs):
            return [
                {
                    k: v
                    for k, v in e.items()
                    if k
                    not in {
                        "interval_version",
                        "teaching_intervals",
                        "occupied_intervals",
                        "break_intervals",
                    }
                }
                for e in real_expand(*args, **kwargs)
            ]

        with monkeypatch.context() as old:
            old.setattr(course_changes, "expand_calendar", legacy_expand)
            draft = change(c, h, cid).json()
        assert confirm(c, h, draft).status_code == 409
        assert not c.get("/api/course-changes").json()
