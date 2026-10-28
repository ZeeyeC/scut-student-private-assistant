from copy import deepcopy
from datetime import datetime
from uuid import uuid4

import pytest

from app import planner
from app.planner import build_plan, instant
from tests.test_foundation import make_client, register_login
from tests.test_planner import fixture


def spec(**changes):
    return {
        "title": "不可安排",
        "timezone": "Asia/Shanghai",
        "starts_at": "2026-10-14T14:00:00+08:00",
        "ends_at": "2026-10-14T17:00:00+08:00",
        **changes,
    }


def protected(**changes):
    return {
        "id": "protected",
        "revision": 1,
        "data": {
            **spec(),
            "active": True,
            "confirmed": True,
            **changes,
        },
    }


def write(c, h, path, body, method="POST", key=None):
    return c.request(
        method,
        "/api" + path,
        json=body,
        headers={
            **h,
            "Idempotency-Key": key or str(uuid4()),
        },
    )


def draft(c, h, **changes):
    r = write(c, h, "/drafts/scheduling-constraint", {"constraint": spec(**changes)})
    assert r.status_code == 200, r.text
    return r.json()


def confirm(c, h, d, **kwargs):
    return write(
        c, h, f"/drafts/{d['id']}/confirm", {"revision": d["revision"]}, **kwargs
    )


def resources(c, kind):
    return [
        r for r in c.get("/api/data-export").json()["resources"] if r["kind"] == kind
    ]


def seed_work(c, h):
    s = c.get("/api/settings").json()
    s["data"].update(
        week1_monday="2026-10-12",
        study_windows=[{"start": "09:00", "end": "18:00"}],
        daily_limit_minutes=600,
        periods={"1": {"start": "09:00", "end": "10:00"}},
    )
    assert write(c, h, "/settings", s, "PUT").status_code == 200
    course = write(
        c,
        h,
        "/drafts/timetable",
        {
            "semester_label": "合成",
            "courses": [
                {
                    "source_key": "math",
                    "name": "高数",
                    "weekday": 3,
                    "weeks": [1],
                    "periods": [1],
                }
            ],
        },
    ).json()
    assert confirm(c, h, course).status_code == 200
    task = write(
        c,
        h,
        "/drafts/assignment",
        {"items": [{"title": "练习", "due_at": "2026-10-14T18:00:00+08:00"}]},
    ).json()
    tid = confirm(c, h, task).json()["saved_ids"][0]
    t = c.get(f"/api/tasks/{tid}").json()
    response = write(
        c,
        h,
        f"/tasks/{tid}/step-drafts",
        {
            "task_revision": t["revision"],
            "steps": [
                {
                    "key": key,
                    "title": "做练习",
                    "description": "合成练习",
                    "estimated_minutes": 180,
                    "dependency_keys": [],
                    "acceptance_criteria": ["完成"],
                }
                for key in ("a", "b")
            ],
        },
    )
    assert response.status_code == 200, response.text
    step = response.json()
    assert confirm(c, h, step).status_code == 200


def test_hard_windows_capacity_and_explanations_are_deterministic():
    p = fixture()
    p["steps"] = p["steps"][:1]
    p["steps"][0]["data"]["estimated_minutes"] = 360
    p["settings"]["daily_limit_minutes"] = 600
    p["constraints"] = [protected()]
    r = build_plan(p)
    assert r == build_plan(deepcopy(p))
    assert r["unscheduled"][0]["remaining_minutes"] == 130
    assert "禁排" in r["unscheduled"][0]["reason"]
    assert r["protected_windows"][0]["id"] == "protected"
    for b in r["blocks"]:
        assert instant(b["ends_at"]) <= instant(spec()["starts_at"]) or instant(
            b["starts_at"]
        ) >= instant(spec()["ends_at"])
        assert b["explanation"]["constraint_revisions"] == {"protected": 1}
        assert b["explanation"]["task_id"] == "t1"
        assert b["explanation"]["reasons"]


@pytest.mark.parametrize("state", [{"active": False}, {"confirmed": False}])
def test_inactive_or_unconfirmed_windows_do_not_reduce_capacity(state):
    p = fixture()
    baseline = build_plan(p)
    p["constraints"] = [protected(**state)]
    assert build_plan(p) == baseline


def test_locked_conflict_is_preserved_reported_and_not_treated_as_valid_work():
    p = fixture()
    p["constraints"] = [protected()]
    p["preserved_blocks"] = [
        {
            "id": "locked",
            "task_id": "t1",
            "step_id": "a",
            "title": "锁定练习",
            "starts_at": "2026-10-14T14:00:00+08:00",
            "ends_at": "2026-10-14T15:00:00+08:00",
            "locked": True,
            "status": "suggested",
        }
    ]
    p["current_blocks"] = deepcopy(p["preserved_blocks"])
    r = build_plan(p)
    assert r["blocks"] == p["preserved_blocks"]
    assert any("禁排" in w and "解锁" in w for w in r["warnings"])
    assert r["unscheduled"][0]["remaining_minutes"] == 120
    assert not r["removed_blocks"]


def test_overnight_utc_interval_is_respected_in_another_user_timezone():
    p = fixture()
    p.update(
        now_utc=datetime.fromisoformat("2026-10-14T00:00:00Z"),
        occurrences=[],
        constraints=[
            protected(starts_at="2026-10-14T00:00:00Z", ends_at="2026-10-15T00:00:00Z")
        ],
    )
    r = build_plan(p)
    assert r["blocks"] == []
    assert sum(u["remaining_minutes"] for u in r["unscheduled"]) == 180


@pytest.mark.parametrize(
    "changes",
    [
        {"timezone": "not/a-zone"},
        {"title": " "},
        {"ends_at": "2026-10-14T13:00:00+08:00"},
        {"starts_at": "2026-10-14T14:00:00"},
        {"strength": "soft"},
        {"recurrence": "weekly"},
        {"confirmed": True},
    ],
)
def test_invalid_or_unsupported_intervals_fail_without_partial_facts(tmp_path, changes):
    with make_client(tmp_path) as c:
        h = register_login(c)
        assert (
            write(
                c, h, "/drafts/scheduling-constraint", {"constraint": spec(**changes)}
            ).status_code
            == 422
        )
        assert c.get("/api/drafts").json() == []
        assert c.get("/api/scheduling-constraints").json() == []


def test_constraint_confirmation_edit_disable_replay_and_restart(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = draft(c, h)
        assert c.get("/api/scheduling-constraints").json() == []
        assert resources(c, "planning_event") == []
        first = confirm(c, h, d, key="save")
        assert first.status_code == 200
        assert confirm(c, h, d, key="save").json() == first.json()
        assert confirm(c, h, d, key="second-save").json() == first.json()
        row = c.get("/api/scheduling-constraints").json()[0]
        assert len(resources(c, "planning_event")) == 1
        assert row["data"]["confirmed"] is True and row["data"]["active"] is True
        payload = {
            "constraint": spec(title="休息"),
            "constraint_id": row["id"],
            "constraint_revision": row["revision"],
        }
        edit = write(c, h, "/drafts/scheduling-constraint", payload).json()
        assert c.get("/api/scheduling-constraints").json()[0] == row
        assert confirm(c, h, edit).status_code == 200
        changed = c.get("/api/scheduling-constraints").json()[0]
        assert changed["id"] == row["id"] and changed["revision"] == 2
        path = f"/scheduling-constraints/{row['id']}"
        assert (
            write(c, h, path, {"revision": 1, "active": False}, "PATCH").status_code
            == 409
        )
        disabled = write(
            c, h, path, {"revision": 2, "active": False}, "PATCH", key="disable"
        )
        assert disabled.status_code == 200
        assert (
            write(
                c, h, path, {"revision": 2, "active": False}, "PATCH", key="disable"
            ).json()
            == disabled.json()
        )
        assert len(resources(c, "planning_event")) == 3
        cookie = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert c.get("/api/scheduling-constraints").json() == [disabled.json()]
        assert len(resources(c, "planning_event")) == 3


def test_target_revision_cannot_be_silently_rebased_or_cross_owner(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = draft(c, h)
        rid = confirm(c, h, d).json()["saved_ids"][0]
        edit = write(
            c,
            h,
            "/drafts/scheduling-constraint",
            {
                "constraint": spec(title="修改"),
                "constraint_id": rid,
                "constraint_revision": 1,
            },
        ).json()
        assert (
            write(
                c,
                h,
                f"/drafts/{edit['id']}",
                {
                    "revision": edit["revision"],
                    "payload": {
                        **edit["data"]["payload"],
                        "constraint_id": None,
                        "constraint_revision": None,
                    },
                },
                "PUT",
            ).status_code
            == 422
        )
        assert (
            write(
                c,
                h,
                f"/scheduling-constraints/{rid}",
                {"revision": 1, "active": False},
                "PATCH",
            ).status_code
            == 200
        )
        assert confirm(c, h, edit).status_code == 409
        assert len(resources(c, "planning_event")) == 2
        assert c.get(f"/api/drafts/{edit['id']}").json()["data"]["status"] == "pending"
        c.post("/api/auth/logout", headers=h)
        other = register_login(c, "other@example.com")
        assert c.get("/api/scheduling-constraints").json() == []
        assert (
            write(
                c,
                other,
                f"/scheduling-constraints/{rid}",
                {"revision": 2, "active": True},
                "PATCH",
            ).status_code
            == 404
        )
        assert (
            write(
                c,
                other,
                "/drafts/scheduling-constraint",
                {"constraint": spec(), "constraint_id": rid, "constraint_revision": 2},
            ).status_code
            == 404
        )


def test_plan_confirmation_version_guard_atomic_snapshot_and_no_false_reminder(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        before = c.get("/api/courses").json()
        old = write(c, h, "/plan-drafts", {"horizon_days": 1}).json()
        d = draft(c, h)
        assert confirm(c, h, d).status_code == 200
        assert confirm(c, h, old).status_code == 409
        assert resources(c, "plan_snapshot") == []
        assert c.get("/api/plan-blocks").json() == []
        plan = write(c, h, "/plan-drafts", {"horizon_days": 1}).json()
        payload = plan["data"]["payload"]
        assert sum(u["remaining_minutes"] for u in payload["unscheduled"]) == 70
        assert c.get("/api/plan-blocks").json() == []
        assert confirm(c, h, plan).status_code == 200
        saved = c.get("/api/plan-blocks").json()
        assert saved
        assert confirm(c, h, plan).status_code == 200
        snapshots = resources(c, "plan_snapshot")
        assert len(snapshots) == 1
        assert snapshots[0]["data"]["approved_plan"] == payload
        assert snapshots[0]["data"]["inputs"]["constraints"][0]["data"]["confirmed"]
        assert len(resources(c, "planning_event")) == 2
        # Recomputing an unchanged future plan keeps stable slot IDs.
        second = write(c, h, "/plan-drafts", {"horizon_days": 1}).json()
        assert set(second["data"]["payload"]["changes"]["retained_ids"]) == {
            b["id"] for b in saved
        }
        assert second["data"]["payload"]["changes"]["removed_ids"] == []
        # Simulate failure after the snapshot insert; all facts must roll back.
        from fastapi import HTTPException

        original_snapshot = planner.save_snapshot

        async def interrupted_snapshot(*args, **kwargs):
            await original_snapshot(*args, **kwargs)
            raise HTTPException(503, "合成测试：保存中断")

        with monkeypatch.context() as failure:
            failure.setattr(planner, "save_snapshot", interrupted_snapshot)
            assert confirm(c, h, second, key="recover-plan").status_code == 503
        assert c.get("/api/plan-blocks").json() == saved
        assert len(resources(c, "plan_snapshot")) == 1
        assert len(resources(c, "planning_event")) == 2
        assert (
            c.get(f"/api/drafts/{second['id']}").json()["data"]["status"] == "pending"
        )
        assert confirm(c, h, second, key="recover-plan").status_code == 200
        assert len(resources(c, "plan_snapshot")) == 2
        assert c.get("/api/courses").json() == before
        constraint = c.get("/api/scheduling-constraints").json()[0]
        from app import schedule_reminders

        monkeypatch.setattr(
            schedule_reminders,
            "now",
            lambda: datetime.fromisoformat("2026-10-14T13:57:00+08:00"),
        )
        assert c.get("/api/schedule-reminders").json() == []
        assert (
            c.get(
                "/api/schedule-shortcut",
                params={
                    "event_id": constraint["id"],
                    "starts_at": constraint["data"]["starts_at"],
                },
            ).status_code
            == 404
        )
        events = c.get("/api/calendar-events?start=2026-10-14&end=2026-10-14").json()[
            "events"
        ]
        assert any(e["kind"] == "scheduling_constraint" for e in events)


def test_demo22_resource_payloads_are_unchanged_on_start_and_backup_restore(tmp_path):
    import sqlite3

    from app.backup import backup, restore

    def saved_rows(path):
        with sqlite3.connect(path) as db:
            return db.execute(
                "select id, owner_id, kind, revision, data from resources order by id"
            ).fetchall()

    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        cookie = dict(c.cookies)
    database = tmp_path / "test.db"
    legacy = saved_rows(database)
    assert all(
        row[2] not in ("planning_event", "plan_snapshot", "scheduling_constraint")
        for row in legacy
    )
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert c.get("/api/scheduling-constraints").json() == []
        assert saved_rows(database) == legacy
        csrf = c.get("/api/csrf").json()["csrf_token"]
        h = {"X-CSRF-Token": csrf, "Origin": "http://testserver"}
        d = draft(c, h)
        assert confirm(c, h, d).status_code == 200
    upgraded = saved_rows(database)
    package = tmp_path / "backup.zip"
    backup(database, tmp_path / "agent.db", tmp_path / "uploads", package)
    target = tmp_path / "restored"
    restore(package, target)
    assert saved_rows(target / "campus.db") == upgraded
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert len(c.get("/api/scheduling-constraints").json()) == 1
    assert saved_rows(database) == upgraded
