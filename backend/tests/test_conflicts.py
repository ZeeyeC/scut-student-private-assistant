"""Deterministic conflict checks on synthetic fixtures, no live model calls."""

from copy import deepcopy

import pytest

from app.calendar import expand_calendar
from app.conflicts import detect_conflicts
from app.contracts import StudentSettings
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import confirm, seed_work, write
from tests.test_timetable_recognition import (
    FakeTimetableVision,
    candidate,
    edit,
    recognize,
    reviewed,
    upload,
)


def event(rid, start="09:00", end="10:00", campus="五山", day="2026-10-14", **extra):
    return {
        "id": rid,
        "course_id": rid,
        "title": rid,
        "kind": "course",
        "campus": campus,
        "starts_at": f"{day}T{start}:00+08:00",
        "ends_at": f"{day}T{end}:00+08:00",
        **extra,
    }


def cfg(**extra):
    return StudentSettings(**extra).model_dump(mode="json")


def issues(events, **settings):
    return detect_conflicts(events, cfg(**settings))["issues"]


def rule(a="五山", b="大学城", minutes=40):
    return {"from_campus": a, "to_campus": b, "minutes": minutes}


def test_overlap_is_half_open_and_compares_instants_with_offsets():
    a, b = event("a"), event("b", "10:00", "11:00")
    assert issues([a, b]) == []
    b.update(starts_at="2026-10-14T01:30:00+00:00", ends_at="2026-10-14T02:30:00+00:00")
    result = issues([b, a])
    assert [i["code"] for i in result] == ["overlap"]
    assert result[0]["overlap_starts_at"] == "2026-10-14T01:30:00+00:00"


def test_long_fixed_event_reports_each_contained_course_and_preserves_inputs():
    fixed = event("fixed", "08:00", "12:00", kind="fixed_event")
    events = [fixed, event("a"), event("b", "10:00", "11:00")]
    before = deepcopy(events)
    result = issues(events)
    assert len([i for i in result if i["code"] == "overlap"]) == 2
    assert events == before


def test_nonconsecutive_free_gap_is_not_a_conflict_but_adjacent_break_is():
    s = cfg(
        week1_monday="2026-10-12",
        periods={
            1: {"start": "09:00", "end": "09:40"},
            2: {"start": "10:00", "end": "10:40"},
            3: {"start": "11:00", "end": "11:40"},
        },
    )
    course = {
        "id": "split",
        "data": {
            "name": "高数",
            "weekday": 3,
            "weeks": [1],
            "periods": [1, 3],
            "campus": "五山",
        },
    }
    from datetime import date

    for periods, expected in [([1, 3], 0), ([1, 2], 1)]:
        course["data"]["periods"] = periods
        courses = expand_calendar(
            s, [course], [], date(2026, 10, 14), date(2026, 10, 14)
        )
        result = detect_conflicts(
            courses + [event("fixed", "09:45", "09:55", kind="fixed_event")], s
        )
        assert result["conflict_count"] == expected


def test_confirmed_directional_transfer_reports_exact_shortfall_and_equality_passes():
    events = [event("a"), event("b", "10:10", "11:00", campus="大学城")]
    result = issues(events, campus_transfers=[rule()])
    assert len(result) == 1 and result[0]["code"] == "transfer_shortfall"
    assert (
        result[0]["required_minutes"],
        result[0]["available_minutes"],
        result[0]["shortfall_minutes"],
    ) == (40, 10, 30)
    assert result[0]["basis"] == "user_confirmed"
    events[1]["starts_at"] = "2026-10-14T10:40:00+08:00"
    assert not issues(events, campus_transfers=[rule()])
    events[0]["campus"], events[1]["campus"] = "大学城", "五山"
    assert issues(events, campus_transfers=[rule()])[0]["code"] == "unknown_transfer"


@pytest.mark.parametrize(
    "campus,code",
    [
        (None, "unknown_campus"),
        ("", "unknown_campus"),
        (" 大学城 ", "unknown_transfer"),
    ],
)
def test_unknown_campus_and_missing_direction_never_claim_reachability(campus, code):
    report = issues([event("a"), event("b", "10:10", "11:00", campus=campus)])
    assert report[0]["severity"] == "pending" and report[0]["code"] == code


def test_overnight_gap_is_not_a_transfer_and_overlap_cluster_has_no_guessed_departure():
    assert not issues(
        [event("a"), event("b", "10:10", "11:00", campus="大学城", day="2026-10-15")]
    )
    result = issues(
        [
            event("a", "09:00", "11:00"),
            event("b", "10:00", "10:30", campus="国际"),
            event("c", "11:10", "12:00", campus="大学城"),
        ]
    )
    assert {i["code"] for i in result} == {"overlap", "unknown_departure"}


@pytest.mark.parametrize(
    "rules",
    [
        [rule(minutes=0)],
        [rule(minutes=True)],
        [rule(minutes=1.5)],
        [rule(minutes=361)],
        [rule(a=" ")],
        [rule(a="五山", b="五山")],
        [rule(), rule()],
    ],
)
def test_invalid_or_duplicated_transfer_facts_rejected(rules):
    with pytest.raises(ValueError):
        StudentSettings(campus_transfers=rules)


def preview(c, h, d, payload=None):
    r = write(
        c,
        h,
        f"/drafts/{d['id']}/conflict-preview",
        {"revision": d["revision"], "payload": payload or d["data"]["payload"]},
    )
    assert r.status_code == 200, r.text
    return r.json()


def timetable(c, h, **changes):
    course = {
        "source_key": "second",
        "name": "大学城英语",
        "campus": "大学城",
        "weekday": 3,
        "weeks": [1],
        "periods": [2],
        **changes,
    }
    r = write(
        c, h, "/drafts/timetable", {"semester_label": "合成课表", "courses": [course]}
    )
    assert r.status_code == 200, r.text
    return r.json()


def setup(c, h):
    seed_work(c, h)
    s = c.get("/api/settings").json()
    s["data"]["periods"]["2"] = {"start": "10:10", "end": "11:00"}
    s["data"]["campus_transfers"] = [rule()]
    assert write(c, h, "/settings", s, "PUT").status_code == 200
    # Explicitly set the existing course's campus through the usual reviewed edit.
    first = c.get("/api/courses").json()[0]["data"]
    first["campus"] = "五山"
    d = write(
        c, h, "/drafts/timetable", {"semester_label": "合成课表", "courses": [first]}
    ).json()
    assert confirm(c, h, d).status_code == 200


def test_manual_preview_is_readonly_ack_receipt_survives_restart_and_is_idempotent(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        setup(c, h)
        before = c.get("/api/courses").json()
        d = timetable(c, h)
        report = preview(c, h, d)
        assert report["issues"][0]["shortfall_minutes"] == 30
        assert c.get("/api/courses").json() == before
        body = {"revision": d["revision"], "conflict_token": report["conflict_token"]}
        saved = write(c, h, f"/drafts/{d['id']}/confirm", body, key="save-reviewed")
        assert saved.status_code == 200, saved.text
        summary = saved.json()
        assert (
            summary["conflict_reviewed"]
            and summary["conflict_report"]["conflict_count"] == 1
        )
        assert (
            write(c, h, f"/drafts/{d['id']}/confirm", body, key="save-reviewed").json()
            == summary
        )
        cookie = dict(c.cookies)
        assert (
            c.get("/api/calendar-events?start=2026-10-14&end=2026-10-14").json()[
                "conflict_report"
            ]["issues"][0]["shortfall_minutes"]
            == 30
        )
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert c.get(f"/api/drafts/{d['id']}").json()["data"]["summary"] == summary
        assert c.get("/api/settings").json()["data"]["campus_transfers"] == [rule()]


def test_fixed_event_preview_rejects_stale_facts_and_edited_payload_without_partial_save(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        setup(c, h)
        d = write(
            c,
            h,
            "/drafts/calendar-event",
            {
                "title": "固定会议",
                "starts_at": "2026-10-14T09:15:00+08:00",
                "ends_at": "2026-10-14T09:45:00+08:00",
            },
        ).json()
        report = preview(c, h, d)
        assert report["conflict_count"] == 1
        body = {"revision": d["revision"], "conflict_token": report["conflict_token"]}
        assert (
            write(
                c,
                h,
                "/fixed-events",
                {
                    "title": "新事项",
                    "starts_at": "2026-10-14T12:00:00+08:00",
                    "ends_at": "2026-10-14T13:00:00+08:00",
                },
            ).status_code
            == 200
        )
        assert write(c, h, f"/drafts/{d['id']}/confirm", body).status_code == 409
        assert len(c.get("/api/fixed-events").json()) == 1
        report = preview(c, h, d)
        payload = {**d["data"]["payload"], "title": "改名会议"}
        edited = write(
            c,
            h,
            f"/drafts/{d['id']}",
            {"revision": d["revision"], "payload": payload},
            "PUT",
        ).json()
        body = {
            "revision": edited["revision"],
            "conflict_token": report["conflict_token"],
        }
        assert write(c, h, f"/drafts/{d['id']}/confirm", body).status_code == 409
        report = preview(c, h, edited)
        body["conflict_token"] = report["conflict_token"]
        assert write(c, h, f"/drafts/{d['id']}/confirm", body).status_code == 200


@pytest.mark.parametrize("kind", ["timetable_text", "timetable_recognition"])
def test_text_and_image_candidates_share_manual_conflicts_and_exact_dedup(
    tmp_path, kind
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        setup(c, h)
        if kind == "timetable_recognition":
            c.app.state.gateway = FakeTimetableVision(
                [
                    candidate(
                        name="大学城英语",
                        campus="大学城",
                        weekday=3,
                        weeks_text="1周",
                        periods=[2],
                    )
                ]
            )
            job = recognize(c, h, upload(c, h))
            d = c.get("/api/drafts/" + job["data"]["draft_id"]).json()
        else:
            # Tool implementation, no model: exercise the same text draft contract.
            import asyncio

            from app import imports
            from app.timetable_recognition import merge_pages

            payload = merge_pages(
                [
                    {
                        "semester_label": "合成",
                        "candidates": [
                            candidate(
                                name="大学城英语",
                                campus="大学城",
                                weekday=3,
                                weeks_text="1周",
                                periods=[2],
                            )
                        ],
                        "warnings": [],
                    }
                ],
                20,
            )
            owner = c.get("/api/me").json()["id"]

            async def create():
                async with c.app.state.sessions() as db:
                    result = await imports.create_draft(
                        db, str(owner), kind, payload, {"messages": []}
                    )
                    await db.commit()
                    return result

            d = asyncio.run(create())
        d = edit(c, h, d, reviewed(d))
        result = preview(c, h, d)
        assert result["issues"][0]["code"] == "transfer_shortfall"
        assert result["issues"][0]["shortfall_minutes"] == 30
        assert confirm(c, h, d).status_code == 200
        # A reused, exact course keeps its ID and reports only its real conflicts.
        assert len(c.get("/api/courses").json()) == 2
        if kind == "timetable_recognition":
            job = recognize(c, h, upload(c, h))
            again = c.get("/api/drafts/" + job["data"]["draft_id"]).json()
        else:
            again = asyncio.run(create())
        again = edit(c, h, again, reviewed(again))
        assert [i["code"] for i in preview(c, h, again)["issues"]] == [
            "transfer_shortfall"
        ]
        assert confirm(c, h, again).status_code == 200
        assert len(c.get("/api/courses").json()) == 2


def test_course_change_rechecks_new_campus_and_unknown_room_move_without_guess(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        setup(c, h)
        assert confirm(c, h, timetable(c, h)).status_code == 200
        cid = c.get("/api/courses").json()[0]["id"]
        d = write(
            c,
            h,
            "/drafts/course-change",
            {
                "course_id": cid,
                "original_date": "2026-10-14",
                "action": "move",
                "starts_at": "2026-10-14T09:00:00+08:00",
                "ends_at": "2026-10-14T10:00:00+08:00",
                "location": "新教室",
                "campus": "大学城",
                "reason": "教师通知同校区",
            },
        ).json()
        assert preview(c, h, d)["issues"] == []
        assert confirm(c, h, d).status_code == 200
        occurrences = c.get("/api/occurrences?start=2026-10-14&end=2026-10-14").json()
        assert occurrences[0]["campus"] == "大学城"
        other = write(
            c,
            h,
            "/drafts/course-change",
            {
                "course_id": cid,
                "original_date": "2026-10-14",
                "action": "move",
                "starts_at": "2026-10-14T09:00:00+08:00",
                "ends_at": "2026-10-14T10:00:00+08:00",
                "location": "未知校区教室",
                "reason": "教师待补充校区",
            },
        ).json()
        assert preview(c, h, other)["issues"][0]["code"] == "unknown_campus"


def test_conflict_preview_owner_revision_and_old_client_receipt(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        setup(c, h)
        d = timetable(c, h, periods=[1])
        assert preview(c, h, d)["issues"][0]["code"] == "overlap"
        assert confirm(c, h, d).json()["conflict_reviewed"] is False
        # An older client still receives the warning and saves a fixed fact;
        # the desktop UI always requires the current, payload-bound review.
        assert c.post("/api/auth/logout", headers=h).status_code == 204
        h = register_login(c, "other@example.com")
        r = write(
            c,
            h,
            f"/drafts/{d['id']}/conflict-preview",
            {"revision": d["revision"], "payload": d["data"]["payload"]},
        )
        assert r.status_code == 404


def test_missing_clock_mapping_remains_explicitly_incomplete_without_guessing(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = timetable(c, h)
        report = preview(c, h, d)
        assert report["complete"] is False and report["pending_count"] == 1
        assert "第一周周一" in report["configuration_warnings"][0]
        assert not c.get("/api/courses").json()
        result = write(
            c,
            h,
            f"/drafts/{d['id']}/confirm",
            {"revision": d["revision"], "conflict_token": report["conflict_token"]},
        )
        assert result.status_code == 200
        agenda = c.get("/api/calendar-events?start=2026-10-14&end=2026-10-14").json()
        assert agenda["warnings"]


def test_transfer_matrix_change_invalidates_fixed_fact_review_and_preserves_replay_hash(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        setup(c, h)
        d = write(
            c,
            h,
            "/drafts/calendar-event",
            {
                "title": "晚上固定事项",
                "starts_at": "2026-10-14T18:00:00+08:00",
                "ends_at": "2026-10-14T19:00:00+08:00",
            },
        ).json()
        report = preview(c, h, d)
        s = c.get("/api/settings").json()
        s["data"]["campus_transfers"] = [rule(minutes=50)]
        assert write(c, h, "/settings", s, "PUT").status_code == 200
        assert (
            write(
                c,
                h,
                f"/drafts/{d['id']}/confirm",
                {"revision": d["revision"], "conflict_token": report["conflict_token"]},
            ).status_code
            == 409
        )
        assert c.get("/api/fixed-events").json() == []
        # A null optional token must not change the historical revision-only
        # idempotency payload hash used by older releases.
        assert confirm(c, h, d, key="legacy-confirm").status_code == 200
        retried = write(
            c,
            h,
            f"/drafts/{d['id']}/confirm",
            {"revision": d["revision"], "conflict_token": None},
            key="legacy-confirm",
        )
        assert retried.status_code == 200
