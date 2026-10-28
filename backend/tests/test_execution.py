"""Real SQLite/API acceptance for B1, with isolated synthetic resources."""

from datetime import datetime
from uuid import uuid4

import pytest

from app.db import Resource
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import resources, write


def seed_execution(c, *, spent=0, block_status="suggested"):
    owner = c.get("/api/me").json()["id"]
    ids = {key: str(uuid4()) for key in ("task", "step", "block")}

    async def seed():
        async with c.app.state.sessions() as db:
            db.add_all(
                [
                    Resource(
                        id=ids["task"],
                        owner_id=owner,
                        kind="task",
                        data={
                            "title": "合成执行练习",
                            "status": "open",
                            "priority": 2,
                            "due_at": "2026-12-31T22:00:00+08:00",
                            "requirements": [],
                        },
                    ),
                    Resource(
                        id=ids["step"],
                        owner_id=owner,
                        kind="step",
                        data={
                            "task_id": ids["task"],
                            "title": "合成步骤",
                            "description": "隔离测试",
                            "status": "open",
                            "estimated_minutes": 60,
                            "spent_minutes": spent,
                            "dependency_ids": [],
                            "acceptance_criteria": ["完成练习"],
                        },
                    ),
                    Resource(
                        id=ids["block"],
                        owner_id=owner,
                        kind="plan_block",
                        data={
                            "task_id": ids["task"],
                            "step_id": ids["step"],
                            "title": "练习",
                            "starts_at": "2026-10-14T10:00:00+08:00",
                            "ends_at": "2026-10-14T11:00:00+08:00",
                            "locked": False,
                            "status": block_status,
                        },
                    ),
                ]
            )
            await db.commit()

    c.portal.call(seed)
    c.get("/api/settings")
    return ids


def execution_body(c, ids, **changes):
    task = c.get(f"/api/tasks/{ids['task']}").json()
    step = next(
        s
        for s in c.get(f"/api/tasks/{ids['task']}/steps").json()
        if s["id"] == ids["step"]
    )
    block = next(b for b in c.get("/api/plan-blocks").json() if b["id"] == ids["block"])
    return {
        "client_operation_id": str(uuid4()),
        "execution_id": str(uuid4()),
        "task_id": ids["task"],
        "task_revision": task["revision"],
        "step_id": ids["step"],
        "step_revision": step["revision"],
        "plan_block_id": ids["block"],
        "plan_block_revision": block["revision"],
        "performed_on": "2026-10-14",
        "timezone": "Asia/Shanghai",
        "actual_minutes": 25,
        "feedback": "partial",
        "unfinished_reason": "insufficient_time",
        "task_status": "open",
        **changes,
    }


def summary(c, ids):
    response = c.get(f"/api/tasks/{ids['task']}/execution-summary")
    assert response.status_code == 200, response.text
    return response.json()


def save(c, h, body, **kwargs):
    response = write(c, h, "/executions", body, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def correction(c, ids, **changes):
    return {
        "client_operation_id": str(uuid4()),
        "revision": 1,
        "task_revision": c.get(f"/api/tasks/{ids['task']}").json()["revision"],
        "actual_minutes": 20,
        "feedback": "partial",
        "unfinished_reason": "interrupted",
        **changes,
    }


def test_plan60_actual25_task_open(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        assert summary(c, ids)["actual_minutes"] is None
        saved = save(c, h, execution_body(c, ids))
        assert saved["data"]["actual_minutes"] == 25
        assert summary(c, ids)["actual_minutes"] == 25
        assert summary(c, ids)["planning_spent_minutes"] == 25
        assert c.get(f"/api/tasks/{ids['task']}").json()["data"]["status"] == "open"
        block = c.get("/api/plan-blocks").json()[0]["data"]
        assert block["starts_at"] == "2026-10-14T10:00:00+08:00"
        assert block["ends_at"] == "2026-10-14T11:00:00+08:00"
        assert len(resources(c, "planning_event")) == 1


def test_retry_and_logical_execution_dedupe(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        body = execution_body(c, ids)
        first = save(c, h, body, key="save")
        assert save(c, h, body, key="save") == first
        assert save(c, h, body, key="retry-new-key") == first
        assert (
            write(
                c, h, "/executions", {**body, "actual_minutes": 30}, key="save"
            ).status_code
            == 409
        )
        assert (
            write(
                c, h, "/executions", execution_body(c, ids), key="second-block-feedback"
            ).status_code
            == 409
        )
        assert len(resources(c, "execution")) == 1
        assert len(resources(c, "planning_event")) == 1
        assert summary(c, ids)["actual_minutes"] == 25


def test_correction25_to20_is_auditable(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        first = save(c, h, execution_body(c, ids))
        url = f"/executions/{first['id']}/corrections"
        body = correction(c, ids)
        second = write(c, h, url, body, key="correction")
        assert second.status_code == 200, second.text
        assert write(c, h, url, body, key="retry-correction").json() == second.json()
        assert summary(c, ids)["actual_minutes"] == 20
        history = c.get(f"/api/tasks/{ids['task']}/executions").json()
        assert sorted(r["data"]["actual_minutes"] for r in history) == [20, 25]
        assert second.json()["data"]["supersedes_id"] == first["id"]
        assert write(c, h, url, correction(c, ids)).status_code == 409


def test_record_and_event_rollback_together(tmp_path, monkeypatch):
    from app import execution

    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        before = c.get("/api/settings").json()["revision"]

        async def fail(*args, **kwargs):
            raise RuntimeError("synthetic event failure")

        monkeypatch.setattr(execution, "record_change", fail)
        with pytest.raises(RuntimeError, match="synthetic event"):
            write(c, h, "/executions", execution_body(c, ids), key="failed-write")
        assert summary(c, ids)["actual_minutes"] is None
        assert not resources(c, "execution")
        assert not resources(c, "execution_baseline")
        assert c.get("/api/settings").json()["revision"] == before
        assert (
            c.get(f"/api/tasks/{ids['task']}/steps").json()[0]["data"]["spent_minutes"]
            == 0
        )


def test_execution_invalidates_old_plan(tmp_path, monkeypatch):
    from app import planner

    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        draft = write(
            c, h, "/plan-drafts", {"target_date": "2026-10-14", "horizon_days": 1}
        )
        assert draft.status_code == 200, draft.text
        save(c, h, execution_body(c, ids))
        result = write(
            c,
            h,
            f"/drafts/{draft.json()['id']}/confirm",
            {"revision": draft.json()["revision"]},
        )
        assert result.status_code == 409
        assert len(c.get("/api/plan-blocks").json()) == 1


def test_zero_stale_and_owner_boundaries(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        stale = execution_body(c, ids, step_revision=99)
        assert write(c, h, "/executions", stale).status_code == 409
        other = seed_execution(c)
        mismatch = execution_body(c, ids, step_id=other["step"])
        assert write(c, h, "/executions", mismatch).status_code == 422
        save(c, h, execution_body(c, ids, actual_minutes=0, feedback="not_started"))
        assert summary(c, ids)["actual_minutes"] == 0
        c.post("/api/auth/logout", headers=h)
        other_h = register_login(c, "bob@example.com")
        assert c.get(f"/api/tasks/{ids['task']}/execution-summary").status_code == 404
        assert write(c, other_h, "/executions", stale).status_code == 404


def test_two_stale_entrances_cannot_both_save_the_same_block(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        first = execution_body(c, ids)
        second = execution_body(c, ids, actual_minutes=30)
        save(c, h, first)
        assert write(c, h, "/executions", second).status_code == 409
        assert summary(c, ids)["actual_minutes"] == 25


def test_local_date_across_midnight_and_year_uses_saved_timezone(tmp_path, monkeypatch):
    from app import execution

    monkeypatch.setattr(
        execution, "now", lambda: datetime.fromisoformat("2026-01-01T00:15:00+00:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        settings = c.get("/api/settings").json()
        settings["data"]["timezone"] = "America/Los_Angeles"
        assert write(c, h, "/settings", settings, "PUT").status_code == 200
        future = execution_body(
            c, ids, timezone="America/Los_Angeles", performed_on="2026-01-01"
        )
        assert write(c, h, "/executions", future).status_code == 422
        record = save(c, h, {**future, "performed_on": "2025-12-31"})
        assert record["data"]["performed_on"] == "2025-12-31"
        assert record["data"]["timezone"] == "America/Los_Angeles"
