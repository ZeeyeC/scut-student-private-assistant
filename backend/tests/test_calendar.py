from datetime import date

import pytest

from app.calendar import expand_calendar, parse_week_expression
from tests.test_foundation import make_client, register_login


def test_week_expression_and_uncertain_rejection():
    assert parse_week_expression("1-8,10-16周(单)", 16) == [1, 3, 5, 7, 11, 13, 15]
    assert parse_week_expression("2、4、6周", 16) == [2, 4, 6]
    with pytest.raises(ValueError):
        parse_week_expression("待定", 16)
    with pytest.raises(ValueError):
        parse_week_expression("1-25周", 16)


def test_explicit_conversational_week_ranges_keep_ambiguity_rejection():
    for expression in ("第3至8周", "第3周到第8周", "3～8周", "第3—8周"):
        assert parse_week_expression(expression, 20) == [3, 4, 5, 6, 7, 8]
    for expression in ("第3至8周左右", "下周到期末", "从第3周开始", "8至3周"):
        with pytest.raises(ValueError):
            parse_week_expression(expression, 20)


def test_measured_scut_segment_parity_and_single_week():
    assert parse_week_expression("第13周", 30) == [13]
    assert parse_week_expression("1周,4-10周(双),11-15周(单)", 30) == [
        1,
        4,
        6,
        8,
        10,
        11,
        13,
        15,
    ]
    assert parse_week_expression("2-3周,5-9周(单),12-16周(双)", 30) == [
        2,
        3,
        5,
        7,
        9,
        12,
        14,
        16,
    ]
    assert parse_week_expression("1-16周,21-22周", 30) == list(range(1, 17)) + [21, 22]


def test_occurrences_anchor_exception_and_missing_period():
    s = {
        "timezone": "Asia/Shanghai",
        "week1_monday": "2026-09-07",
        "periods": {"1": {"start": "08:30:00", "end": "09:15:00"}},
        "week_count": 16,
    }
    courses = [
        {
            "id": "c1",
            "data": {
                "name": "数学",
                "weekday": 1,
                "weeks": [1, 3],
                "periods": [1],
                "source_key": "math",
            },
        }
    ]
    got = expand_calendar(s, courses, [], date(2026, 9, 1), date(2026, 9, 30))
    assert [x["starts_at"][:10] for x in got] == ["2026-09-07", "2026-09-21"]
    got = expand_calendar(
        s,
        courses,
        [{"course_id": "c1", "date": "2026-09-07", "cancelled": True}],
        date(2026, 9, 1),
        date(2026, 9, 30),
    )
    assert len(got) == 1
    s["periods"] = {}
    with pytest.raises(ValueError, match="节次"):
        expand_calendar(s, courses, [], date(2026, 9, 1), date(2026, 9, 30))


def test_draft_confirmation_replay_stale_and_owner(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.get("/api/settings")
        payload = {
            "courses": [
                {
                    "source_key": "math",
                    "name": "数学",
                    "weekday": 1,
                    "weeks": [1, 3],
                    "periods": [1],
                    "location": "A101",
                }
            ],
            "completeness": "partial",
            "semester_label": "测试学期",
        }
        d = c.post(
            "/api/drafts/timetable",
            json=payload,
            headers={**h, "Idempotency-Key": "draft"},
        ).json()
        assert c.get("/api/courses").json() == []
        commit = {"revision": d["revision"]}
        url = f"/api/drafts/{d['id']}/confirm"
        a = c.post(url, json=commit, headers={**h, "Idempotency-Key": "save"})
        assert a.status_code == 200
        assert (
            c.post(
                url, json=commit, headers={**h, "Idempotency-Key": "save-again"}
            ).json()
            == a.json()
        )
        assert len(c.get("/api/courses").json()) == 1
        d2 = c.post(
            "/api/drafts/timetable",
            json=payload,
            headers={**h, "Idempotency-Key": "d2"},
        ).json()
        current = c.get("/api/settings").json()
        c.put(
            "/api/settings",
            json=current,
            headers={**h, "Idempotency-Key": "change-settings"},
        )
        assert (
            c.post(
                f"/api/drafts/{d2['id']}/confirm",
                json={"revision": 1},
                headers={**h, "Idempotency-Key": "stale"},
            ).status_code
            == 409
        )
        c.post("/api/auth/logout", headers=h)
        register_login(c, "bob@example.com")
        assert c.get(f"/api/drafts/{d['id']}").status_code == 404
