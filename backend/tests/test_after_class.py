from datetime import datetime
from uuid import uuid4

import pytest

from app import after_class
from tests.test_foundation import make_client, register_login


def clock(monkeypatch, value="2026-10-14T18:30:00+08:00"):
    current = [datetime.fromisoformat(value)]
    monkeypatch.setattr(after_class, "now", lambda: current[0])
    return current


def write(c, h, path, data, method="post", key=None):
    return getattr(c, method)(
        path, json=data, headers={**h, "Idempotency-Key": key or str(uuid4())}
    )


def seed(c, h, daily=180):
    s = c.get("/api/settings").json()
    s["data"].update(
        week1_monday="2026-10-12",
        week_count=20,
        periods={
            "1": {"start": "09:00", "end": "10:00"},
            "2": {"start": "14:00", "end": "15:00"},
            "3": {"start": "17:00", "end": "18:00"},
        },
        study_windows=[{"start": "19:00", "end": "23:00"}],
        daily_limit_minutes=daily,
    )
    assert write(c, h, "/api/settings", s, "put").status_code == 200
    courses = [
        {
            "source_key": f"c{i}",
            "name": name,
            "weekday": 3,
            "weeks": [1],
            "periods": [i],
        }
        for i, name in enumerate(["高等数学", "高等数学", "大学物理"], 1)
    ]
    d = write(
        c, h, "/api/drafts/timetable", {"courses": courses, "semester_label": "测试"}
    ).json()
    assert (
        write(
            c, h, f"/api/drafts/{d['id']}/confirm", {"revision": d["revision"]}
        ).status_code
        == 200
    )
    assert c.get("/api/after-class/preferences").json()["data"]["delay_minutes"] == 30


def opened(c, h):
    r = write(c, h, "/api/after-class/open", {})
    assert r.status_code == 200, r.text
    return r.json()


def answer(ctx, minutes=45, due=None):
    return {
        "course_key": ctx["courses"][0]["key"],
        "status": "homework",
        "items": [
            {"content": "完成第三章练习", "estimated_minutes": minutes, "due_at": due}
        ],
    }


def submit(c, h, ctx, answers, key=None):
    return write(
        c,
        h,
        f"/api/after-class/{ctx['review']['id']}/submit",
        {"revision": ctx["review"]["revision"], "answers": answers},
        key=key,
    )


def test_trigger_boundary_and_course_dedup(tmp_path, monkeypatch):
    current = clock(monkeypatch, "2026-10-14T18:29:59+08:00")
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed(c, h)
        assert not opened(c, h)["due"]
        current[0] = datetime.fromisoformat("2026-10-14T18:30:00+08:00")
        assert c.get("/api/tasks").json() == []
        ctx = opened(c, h)
        assert ctx["due"] and [x["name"] for x in ctx["courses"]] == [
            "高等数学",
            "大学物理",
        ]
        assert opened(c, h)["review"]["id"] == ctx["review"]["id"]


def test_auto_schedule_partial_idempotency_and_preserved_capacity(
    tmp_path, monkeypatch
):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed(c, h, 90)
        ctx = opened(c, h)
        first = submit(c, h, ctx, [answer(ctx, 90)]).json()
        assert not first["complete"] and first["blocks"] and not first["unscheduled"]
        task = c.get("/api/tasks").json()[0]
        assert (
            task["data"]["due_at"] is None
            and "due_at" in task["data"]["uncertain_fields"]
        )
        existing = c.get("/api/plan-blocks").json()
        pending = opened(c, h)
        assert [x["name"] for x in pending["courses"]] == ["大学物理"]
        r = submit(c, h, pending, [answer(pending, 60)], "physics")
        assert r.status_code == 200, r.text
        second = r.json()
        assert second["complete"] and second["blocks"]
        assert all(
            datetime.fromisoformat(b["starts_at"]).date().isoformat() == "2026-10-15"
            for b in second["blocks"]
        )
        blocks = c.get("/api/plan-blocks").json()
        assert all(b in blocks for b in existing)
        assert not opened(c, h)["due"]
        assert submit(c, h, pending, [answer(pending, 60)], "physics").json() == second
        assert submit(c, h, pending, [answer(pending, 60)]).status_code == 409
        assert len(c.get("/api/tasks").json()) == 2
        events = c.get("/api/calendar-events?start=2026-10-14&end=2026-10-20").json()[
            "events"
        ]
        assert sum(e["kind"] == "plan_block" for e in events) == len(blocks)


def test_no_homework_and_draft_survive_restart(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed(c, h)
        ctx = opened(c, h)
        drafts = [answer(ctx)]
        r = write(
            c,
            h,
            f"/api/after-class/{ctx['review']['id']}/draft",
            {"revision": ctx["review"]["revision"], "answers": drafts},
            "put",
        )
        assert r.status_code == 200, r.text
        assert c.get("/api/tasks").json() == []
        cookies = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        h = {
            "Origin": "http://testserver",
            "X-CSRF-Token": c.get("/api/csrf").json()["csrf_token"],
        }
        ctx = opened(c, h)
        assert ctx["review"]["data"]["draft_answers"] == drafts
        answers = [
            {"course_key": x["key"], "status": "none", "items": []}
            for x in ctx["courses"]
        ]
        result = submit(c, h, ctx, answers).json()
        assert (
            result["complete"] and result["blocks"] == [] and result["task_ids"] == []
        )
        assert not opened(c, h)["due"]


def test_updated_timetable_disabled_and_no_courses(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c)
        assert not opened(c, h)["due"]
        seed(c, h)
        ctx = opened(c, h)
        s = c.get("/api/settings").json()
        s["data"]["periods"]["3"]["end"] = "20:00"
        assert write(c, h, "/api/settings", s, "put").status_code == 200
        assert not opened(c, h)["due"]
        assert submit(c, h, ctx, [answer(ctx)]).status_code == 409
        p = c.get("/api/after-class/preferences").json()
        assert (
            write(
                c,
                h,
                "/api/after-class/preferences",
                {"revision": p["revision"], "enabled": False, "delay_minutes": 30},
                "put",
            ).status_code
            == 200
        )
        assert not opened(c, h)["due"]


def test_shortfall_due_and_no_partial_bad_writes(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed(c, h, 15)
        ctx = opened(c, h)
        result = submit(
            c, h, ctx, [answer(ctx, 60, "2026-10-14T20:00:00+08:00")]
        ).json()
        assert result["unscheduled"][0]["remaining_minutes"] == 45
        assert all(
            datetime.fromisoformat(b["ends_at"])
            <= datetime.fromisoformat("2026-10-14T20:00:00+08:00")
            for b in result["blocks"]
        )
        assert len(c.get("/api/tasks").json()) == 1


def test_owner_and_course_isolation(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed(c, h)
        ctx = opened(c, h)
        bad = answer(ctx)
        bad["course_key"] = "foreign"
        assert submit(c, h, ctx, [bad]).status_code == 409
        assert c.get("/api/tasks").json() == []
        assert c.post("/api/auth/logout", headers=h).status_code == 204
        h = register_login(c, "bob@example.com")
        assert submit(c, h, ctx, [answer(ctx)]).status_code == 404


def test_later_open_catches_up_without_backfill(tmp_path, monkeypatch):
    current = clock(monkeypatch, "2026-10-14T18:00:00+08:00")
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed(c, h)
        assert not opened(c, h)["due"]
        current[0] = datetime.fromisoformat("2026-10-15T09:00:00+08:00")
        ctx = opened(c, h)
        assert ctx["due"] and ctx["date"] == "2026-10-14"
        assert (
            c.get("/api/after-class/preferences").json()["data"]["started_on"]
            == "2026-10-14"
        )


@pytest.mark.parametrize(
    "patch",
    [{"estimated_minutes": 0}, {"content": " "}, {"due_at": "2026-10-15T12:00:00"}],
)
def test_invalid_item_rolls_back(tmp_path, monkeypatch, patch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed(c, h)
        ctx = opened(c, h)
        value = answer(ctx)
        value["items"][0].update(patch)
        assert submit(c, h, ctx, [value]).status_code == 422
        assert c.get("/api/tasks").json() == []
