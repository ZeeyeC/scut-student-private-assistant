"""Voluntary timers are resumable observations, never planned-duration guesses."""

from uuid import uuid4

import pytest

from app import execution_timers
from tests.test_execution import execution_body, seed_execution, summary
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import resources, write


@pytest.fixture
def clock(monkeypatch):
    value = [0.0]
    monkeypatch.setattr(execution_timers, "monotonic_seconds", lambda: value[0])
    return value


def start(c, h, ids, **changes):
    body = execution_body(c, ids)
    for key in ("actual_minutes", "feedback", "unfinished_reason", "task_status"):
        body.pop(key, None)
    response = write(c, h, "/execution-timers", {**body, **changes})
    assert response.status_code == 200, response.text
    return response.json()


def command(c, h, timer, action, **changes):
    body = {
        "revision": timer["revision"],
        "client_operation_id": str(uuid4()),
        "action": action,
        **changes,
    }
    response = write(c, h, f"/execution-timers/{timer['id']}/actions", body)
    assert response.status_code == 200, response.text
    return response.json()


def advance(c, h, timer, clock, seconds):
    while seconds:
        delta = min(60, seconds)
        clock[0] += delta
        timer = command(c, h, timer, "heartbeat")
        seconds -= delta
    return timer


def test_pause_does_not_count_and_25_minutes_is_not_task_completion(tmp_path, clock):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        assert summary(c, ids)["actual_minutes"] is None
        timer = advance(c, h, timer, clock, 600)
        timer = command(c, h, timer, "pause")
        clock[0] += 900
        timer = command(c, h, timer, "resume")
        timer = advance(c, h, timer, clock, 900)
        timer = command(c, h, timer, "finish", feedback="partial")
        assert timer["data"]["status"] == "finished"
        assert summary(c, ids)["actual_minutes"] == 25
        assert summary(c, ids)["actual_seconds"] == 1500
        assert c.get(f"/api/tasks/{ids['task']}").json()["data"]["status"] == "open"
        assert resources(c, "execution")[0]["data"]["source"] == "timer"


def test_finish_retry_heartbeat_and_single_running_timer(tmp_path, clock):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        another = seed_execution(c)
        body = execution_body(c, another)
        for key in ("actual_minutes", "feedback", "unfinished_reason", "task_status"):
            body.pop(key, None)
        assert write(c, h, "/execution-timers", body).status_code == 409
        timer = advance(c, h, timer, clock, 60)
        body = {
            "revision": timer["revision"],
            "client_operation_id": "finish-once",
            "action": "finish",
            "feedback": "partial",
        }
        path = f"/execution-timers/{timer['id']}/actions"
        first = write(c, h, path, body, key="finish").json()
        assert write(c, h, path, body, key="finish").json() == first
        assert write(c, h, path, body, key="finish-retry").json() == first
        assert len(resources(c, "execution")) == 1
        assert summary(c, ids)["actual_minutes"] == 1


def test_disconnect_and_boot_change_keep_last_confirmed_duration(tmp_path, clock):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        timer = advance(c, h, timer, clock, 60)
        clock[0] += 3600
        listed = c.get("/api/execution-timers").json()
        current = next(r for r in listed if r["id"] == timer["id"])
        assert current["data"]["status"] == "interrupted"
        assert current["data"]["elapsed_seconds"] == 60
        timer = command(c, h, timer, "finish", feedback="partial")
        assert summary(c, ids)["actual_minutes"] == 1
        second = seed_execution(c)
        timer = start(c, h, second)
        timer = advance(c, h, timer, clock, 60)
        cookies = dict(c.cookies)
    clock[0] += 7200
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        current = next(
            r for r in c.get("/api/execution-timers").json() if r["id"] == timer["id"]
        )
        assert current["data"]["status"] == "interrupted"
        command(c, h, timer, "finish", feedback="partial")
        assert summary(c, second)["actual_seconds"] == 60


def test_switch_to_manual_and_correction_does_not_keep_old_timer_seconds(
    tmp_path, clock
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        timer = advance(c, h, timer, clock, 120)
        assert write(c, h, "/executions", execution_body(c, ids)).status_code == 409
        command(c, h, timer, "finish", feedback="partial", actual_minutes=25)
        record = resources(c, "execution")[0]
        assert record["data"]["source"] == "manual"
        assert summary(c, ids)["actual_minutes"] == 25
        from tests.test_execution import correction

        response = write(
            c, h, f"/executions/{record['id']}/corrections", correction(c, ids)
        )
        assert response.status_code == 200
        assert summary(c, ids)["actual_minutes"] == 20


def test_subminute_sessions_are_summed_before_rounding_and_timer_can_be_corrected(
    tmp_path, clock
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        for _ in range(2):
            timer = start(
                c,
                h,
                ids,
                plan_block_id=None,
                plan_block_revision=None,
                legacy_resolution="separate",
            )
            timer = advance(c, h, timer, clock, 59)
            command(c, h, timer, "finish", feedback="partial")
        assert summary(c, ids)["actual_seconds"] == 118
        assert summary(c, ids)["actual_minutes"] == 1
        records = resources(c, "execution")
        from tests.test_execution import correction

        result = write(
            c,
            h,
            f"/executions/{records[0]['id']}/corrections",
            correction(c, ids, actual_minutes=2),
        )
        assert result.status_code == 200
        assert summary(c, ids)["actual_seconds"] == 179


def test_active_timer_prevents_orphaning_and_task_delete_cleans_timer(tmp_path, clock):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        start(c, h, ids)
        task = c.get(f"/api/tasks/{ids['task']}").json()
        draft = write(
            c,
            h,
            f"/tasks/{ids['task']}/step-drafts",
            {
                "task_revision": task["revision"],
                "steps": [
                    {
                        "key": "a",
                        "title": "new",
                        "description": "new",
                        "estimated_minutes": 30,
                        "dependency_keys": [],
                        "acceptance_criteria": ["done"],
                    }
                ],
            },
        ).json()
        assert (
            write(
                c, h, f"/drafts/{draft['id']}/confirm", {"revision": draft["revision"]}
            ).status_code
            == 409
        )
        assert (
            write(
                c, h, f"/tasks/{ids['task']}", {"revision": task["revision"]}, "DELETE"
            ).status_code
            == 200
        )
        assert not resources(c, "execution_timer")


def test_existing_execution_identity_cannot_start_a_second_timer(tmp_path, clock):
    from tests.test_execution import save

    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        original = execution_body(
            c,
            ids,
            plan_block_id=None,
            plan_block_revision=None,
            legacy_resolution="separate",
        )
        save(c, h, original)
        payload = execution_body(
            c,
            ids,
            plan_block_id=None,
            plan_block_revision=None,
            legacy_resolution="separate",
            execution_id=original["execution_id"],
        )
        for field in ("actual_minutes", "feedback", "unfinished_reason", "task_status"):
            payload.pop(field, None)
        assert write(c, h, "/execution-timers", payload).status_code == 409
        assert not resources(c, "execution_timer")


def test_not_started_cannot_keep_observed_timer_seconds(tmp_path, clock):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        timer = advance(c, h, timer, clock, 59)
        body = {
            "revision": timer["revision"],
            "client_operation_id": str(uuid4()),
            "action": "finish",
            "feedback": "not_started",
        }
        assert (
            write(c, h, f"/execution-timers/{timer['id']}/actions", body).status_code
            == 422
        )
        assert summary(c, ids)["actual_minutes"] is None
        command(c, h, timer, "finish", feedback="not_started", actual_minutes=0)
        assert summary(c, ids)["actual_minutes"] == 0


@pytest.mark.parametrize("last_action", ["discard", "finish"])
def test_start_does_not_replace_legacy_until_an_execution_is_finished(
    tmp_path, clock, last_action
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c, spent=30)
        timer = start(
            c,
            h,
            ids,
            plan_block_id=None,
            plan_block_revision=None,
            legacy_resolution="replace",
        )
        assert summary(c, ids)["legacy_estimated_minutes"] == 30
        assert summary(c, ids)["planning_spent_minutes"] == 30
        assert resources(c, "execution_baseline") == []
        if last_action == "finish":
            command(c, h, timer, "finish", feedback="partial", actual_minutes=25)
            assert summary(c, ids)["legacy_estimated_minutes"] == 0
            assert summary(c, ids)["actual_minutes"] == 25
        else:
            command(c, h, timer, "discard")
            assert summary(c, ids)["legacy_estimated_minutes"] == 30
            assert summary(c, ids)["actual_minutes"] is None


@pytest.mark.parametrize("feedback", ["not_started", "skipped"])
def test_invalid_manual_finish_is_editable_client_error(tmp_path, clock, feedback):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        response = write(
            c,
            h,
            f"/execution-timers/{timer['id']}/actions",
            {
                "revision": timer["revision"],
                "client_operation_id": str(uuid4()),
                "action": "finish",
                "feedback": feedback,
                "actual_minutes": 5,
            },
        )
        assert response.status_code == 422
        assert summary(c, ids)["actual_minutes"] is None
        command(c, h, timer, "finish", feedback=feedback, actual_minutes=0)
        assert summary(c, ids)["actual_minutes"] == 0


@pytest.mark.parametrize("manual", [False, True])
def test_finish_keeps_observed_timezone_after_settings_change(tmp_path, clock, manual):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        timer = advance(c, h, timer, clock, 60)
        settings = c.get("/api/settings").json()
        settings["data"]["timezone"] = "America/Los_Angeles"
        assert write(c, h, "/settings", settings, "PUT").status_code == 200
        command(
            c,
            h,
            timer,
            "finish",
            feedback="partial",
            **({"actual_minutes": 25} if manual else {}),
        )
        record = resources(c, "execution")[0]
        assert record["data"]["timezone"] == "Asia/Shanghai"
        assert record["data"]["performed_on"] == "2026-10-14"
        assert summary(c, ids)["actual_seconds"] == (1500 if manual else 60)


def test_plan_replacement_preserves_unfinished_timer_target(
    tmp_path, clock, monkeypatch
):
    from datetime import datetime

    from app import planner

    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)

        def plan():
            response = write(
                c, h, "/plan-drafts", {"target_date": "2026-10-14", "horizon_days": 7}
            )
            assert response.status_code == 200, response.text
            return response.json()

        draft = plan()
        before = resources(c, "plan_block")
        assert ids["block"] in draft["data"]["payload"]["changes"]["retained_ids"]
        response = write(
            c, h, f"/drafts/{draft['id']}/confirm", {"revision": draft["revision"]}
        )
        assert response.status_code == 200  # unchanged timer target is never replaced
        assert resources(c, "plan_block") == before
        assert any(b["id"] == ids["block"] for b in resources(c, "plan_block"))
        assert len(resources(c, "plan_snapshot")) == 1
        command(c, h, timer, "discard")
        draft = plan()
        assert (
            write(
                c, h, f"/drafts/{draft['id']}/confirm", {"revision": draft["revision"]}
            ).status_code
            == 200
        )
