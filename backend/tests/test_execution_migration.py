"""Legacy inputs remain estimates and cannot double-count precise observations."""

from uuid import uuid4

from app.db import Resource
from tests.test_execution import (
    correction,
    execution_body,
    save,
    seed_execution,
    summary,
)
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import resources, write


def test_legacy_completed_block_replaced_by_actual(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c, spent=60, block_status="completed")
        assert summary(c, ids)["actual_minutes"] is None
        assert summary(c, ids)["legacy_estimated_minutes"] == 60
        first = save(c, h, execution_body(c, ids))
        assert summary(c, ids)["actual_minutes"] == 25
        assert summary(c, ids)["planning_spent_minutes"] == 25
        assert resources(c, "execution_baseline")[0]["data"]["allocations"] == {
            ids["block"]: 60
        }
        assert (
            write(
                c, h, f"/executions/{first['id']}/corrections", correction(c, ids)
            ).status_code
            == 200
        )
        assert summary(c, ids)["planning_spent_minutes"] == 20


def test_estimate_only_step_and_unknown_coverage(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c, spent=40)
        before = resources(c, "execution_baseline")
        assert summary(c, ids)["actual_minutes"] is None
        assert summary(c, ids)["unresolved_legacy_minutes"] == 40
        assert resources(c, "execution_baseline") == before
        body = execution_body(c, ids)
        assert write(c, h, "/executions", body).status_code == 409
        assert not resources(c, "execution_baseline")
        save(c, h, {**body, "legacy_resolution": "replace"})
        assert summary(c, ids)["planning_spent_minutes"] == 25
        assert summary(c, ids)["legacy_estimated_minutes"] == 0


def test_old_spent_patch_preserves_total_semantics(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        save(c, h, execution_body(c, ids))
        step_url = f"/steps/{ids['step']}"
        step = c.get(f"/api/tasks/{ids['task']}/steps").json()[0]
        result = write(
            c, h, step_url, {"revision": step["revision"], "spent_minutes": 60}, "PATCH"
        )
        assert result.status_code == 200, result.text
        assert summary(c, ids)["actual_minutes"] == 25
        assert summary(c, ids)["planning_spent_minutes"] == 60
        assert summary(c, ids)["legacy_estimated_minutes"] == 35
        assert (
            write(
                c,
                h,
                step_url,
                {"revision": result.json()["revision"], "spent_minutes": 10},
                "PATCH",
            ).status_code
            == 422
        )


def test_new_actual_then_old_block_completion_does_not_add_planned_time(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        save(c, h, execution_body(c, ids))
        block = c.get("/api/plan-blocks").json()[0]
        response = write(
            c,
            h,
            f"/plan-blocks/{ids['block']}",
            {"revision": block["revision"], "completed": True},
            "PATCH",
        )
        assert response.status_code == 200
        assert summary(c, ids)["planning_spent_minutes"] == 25
        assert summary(c, ids)["actual_minutes"] == 25


def test_old_block_completion_is_estimate_and_exact_feedback_replaces_it(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        response = write(
            c,
            h,
            f"/plan-blocks/{ids['block']}",
            {"revision": 1, "completed": True},
            "PATCH",
        )
        assert response.status_code == 200, response.text
        assert summary(c, ids)["actual_minutes"] is None
        assert summary(c, ids)["legacy_estimated_minutes"] == 60
        save(c, h, execution_body(c, ids))
        assert summary(c, ids)["planning_spent_minutes"] == 25


def test_task_delete_and_redecompose_preserve_consistency(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        save(c, h, execution_body(c, ids))
        task = c.get(f"/api/tasks/{ids['task']}").json()
        draft = write(
            c,
            h,
            f"/tasks/{ids['task']}/step-drafts",
            {
                "task_revision": task["revision"],
                "steps": [
                    {
                        "key": "new",
                        "title": "新步骤",
                        "description": "不应删除执行关联",
                        "estimated_minutes": 30,
                        "dependency_keys": [],
                        "acceptance_criteria": ["完成"],
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
        assert summary(c, ids)["actual_minutes"] == 25
        task = c.get(f"/api/tasks/{ids['task']}").json()
        assert (
            write(
                c, h, f"/tasks/{ids['task']}", {"revision": task["revision"]}, "DELETE"
            ).status_code
            == 200
        )
        assert not resources(c, "execution")
        assert not resources(c, "execution_baseline")
        assert c.get(f"/api/tasks/{ids['task']}/execution-summary").status_code == 404


def test_persistence_and_task_completion_does_not_create_minutes(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        assert (
            write(
                c,
                h,
                f"/tasks/{ids['task']}",
                {"revision": 1, "status": "completed"},
                "PATCH",
            ).status_code
            == 200
        )
        assert summary(c, ids)["actual_minutes"] is None
        save(c, h, execution_body(c, ids, actual_minutes=0, feedback="not_started"))
        cookies = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        assert summary(c, ids)["actual_minutes"] == 0
        assert len(resources(c, "execution")) == 1


def test_another_old_block_uses_the_same_authoritative_projection(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        save(c, h, execution_body(c, ids))
        block_id = str(uuid4())
        owner = c.get("/api/me").json()["id"]

        async def add_block():
            async with c.app.state.sessions() as db:
                db.add(
                    Resource(
                        id=block_id,
                        owner_id=owner,
                        kind="plan_block",
                        data={
                            "task_id": ids["task"],
                            "step_id": ids["step"],
                            "title": "另一段",
                            "starts_at": "2026-10-14T12:00:00+08:00",
                            "ends_at": "2026-10-14T13:00:00+08:00",
                            "locked": False,
                            "status": "suggested",
                        },
                    )
                )
                await db.commit()

        c.portal.call(add_block)
        assert (
            write(
                c,
                h,
                f"/plan-blocks/{block_id}",
                {"revision": 1, "completed": True},
                "PATCH",
            ).status_code
            == 200
        )
        assert summary(c, ids)["actual_minutes"] == 25
        assert summary(c, ids)["legacy_estimated_minutes"] == 60
        assert summary(c, ids)["planning_spent_minutes"] == 85


def test_step_only_actual_prevents_redecomposition_from_orphaning_facts(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        save(c, h, execution_body(c, ids, plan_block_id=None, plan_block_revision=None))
        task = c.get(f"/api/tasks/{ids['task']}").json()
        draft = write(
            c,
            h,
            f"/tasks/{ids['task']}/step-drafts",
            {
                "task_revision": task["revision"],
                "steps": [
                    {
                        "key": "new",
                        "title": "新步骤",
                        "description": "保留事实",
                        "estimated_minutes": 30,
                        "dependency_keys": [],
                        "acceptance_criteria": ["完成"],
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
