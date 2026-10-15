import pytest

from app import imports, store
from app.db import Resource
from tests.test_agent import ToolModel, wait_run
from tests.test_browser_import import configured_client
from tests.test_calendar_events import post
from tests.test_foundation import make_client, register_login


def delete(c, h, path, revision, key="delete"):
    return c.request(
        "DELETE",
        path,
        json={"revision": revision},
        headers={**h, "Idempotency-Key": key},
    )


def assignment(c, h, title="删除测试待办", key="task"):
    draft = post(
        c, h, "/api/drafts/assignment", {"items": [{"title": title}]}, key
    ).json()
    result = post(
        c, h, f"/api/drafts/{draft['id']}/confirm", {"revision": 1}, key + "save"
    )
    assert result.status_code == 200
    task = c.get(f"/api/tasks/{result.json()['saved_ids'][0]}").json()
    return task, draft


def test_task_delete_cascades_and_invalidates_proposals_without_resurrection(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, confirmed = assignment(c, h)
        other, _ = assignment(c, h, "保留的待办", "other")
        owner = c.get("/api/me").json()["id"]

        async def seed():
            async with c.app.state.sessions() as db:
                for rid, kind, data in [
                    ("step-delete", "step", {"task_id": task["id"]}),
                    ("step-keep", "step", {"task_id": other["id"]}),
                    (
                        "block-delete",
                        "plan_block",
                        {
                            "task_id": task["id"],
                            "step_id": "step-delete",
                            "locked": False,
                        },
                    ),
                    (
                        "block-locked",
                        "plan_block",
                        {
                            "task_id": task["id"],
                            "step_id": "step-delete",
                            "locked": True,
                        },
                    ),
                    (
                        "block-completed",
                        "plan_block",
                        {
                            "task_id": task["id"],
                            "step_id": "step-delete",
                            "status": "completed",
                        },
                    ),
                    (
                        "block-keep",
                        "plan_block",
                        {"task_id": other["id"], "step_id": "step-keep"},
                    ),
                    ("asset-keep", "asset", {"filename": "shared.png"}),
                ]:
                    db.add(Resource(id=rid, owner_id=owner, kind=kind, data=data))
                proposal = await imports.create_draft(
                    db,
                    owner,
                    "decomposition",
                    {
                        "task_id": task["id"],
                        "task_revision": task["revision"],
                        "steps": [
                            {
                                "key": "new",
                                "title": "步骤",
                                "description": "完成步骤",
                                "estimated_minutes": 30,
                                "dependency_keys": [],
                                "acceptance_criteria": ["完成"],
                            }
                        ],
                    },
                )
                plan = await imports.create_draft(
                    db, owner, "plan", {"blocks": [], "unscheduled": []}
                )
                revision = (await store.settings(db, owner)).revision
                await db.commit()
                return proposal, plan, revision

        proposal, plan, settings_revision = c.portal.call(seed)
        url = f"/api/tasks/{task['id']}"
        assert delete(c, h, url, task["revision"] + 1, "stale").status_code == 409
        assert c.get(url).status_code == 200
        result = delete(c, h, url, task["revision"])
        assert result.status_code == 200
        assert result.json()["deleted"] is True
        assert delete(c, h, url, task["revision"]).json() == result.json()
        assert delete(c, h, url, task["revision"] + 1).status_code == 409
        assert c.get(url).status_code == 404
        assert [t["id"] for t in c.get("/api/tasks").json()] == [other["id"]]
        assert c.get("/api/drafts").json() == []
        for draft in [proposal, plan]:
            assert (
                post(
                    c,
                    h,
                    f"/api/drafts/{draft['id']}/confirm",
                    {"revision": draft["revision"]},
                    draft["id"],
                ).status_code
                == 409
            )
        # An old confirmation receipt stays historical; it cannot recreate a task.
        assert (
            post(
                c,
                h,
                f"/api/drafts/{confirmed['id']}/confirm",
                {"revision": 1},
                "old-confirm",
            ).status_code
            == 200
        )
        assert c.get(url).status_code == 404
        assert (
            c.patch(
                url,
                json={"revision": task["revision"], "status": "completed"},
                headers={**h, "Idempotency-Key": "old-update"},
            ).status_code
            == 404
        )

        async def inspect():
            async with c.app.state.sessions() as db:
                assert [s.id for s in await store.rows(db, owner, "step")] == [
                    "step-keep"
                ]
                assert [b.id for b in await store.rows(db, owner, "plan_block")] == [
                    "block-keep"
                ]
                assert await db.get(Resource, "asset-keep") is not None
                assert (
                    await store.settings(db, owner)
                ).revision == settings_revision + 1

        c.portal.call(inspect)


@pytest.mark.parametrize(
    "kind", ["assignment", "calendar_event", "timetable", "decomposition", "plan"]
)
def test_all_pending_draft_kinds_can_be_deleted_without_changing_saved_facts(
    tmp_path, kind
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, confirmed = assignment(c, h)
        owner = c.get("/api/me").json()["id"]
        payloads = {
            "assignment": {"items": [{"title": "未保存的任务"}]},
            "calendar_event": {
                "title": "未保存事项",
                "starts_at": "2026-10-16T17:00:00+08:00",
                "ends_at": "2026-10-16T18:00:00+08:00",
            },
            "timetable": {
                "semester_label": "测试学期",
                "courses": [
                    {
                        "source_key": "test",
                        "name": "测试课程",
                        "weekday": 1,
                        "weeks": [1],
                        "periods": [1],
                    }
                ],
            },
            "decomposition": {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "steps": [
                    {
                        "key": "new",
                        "title": "步骤",
                        "description": "完成步骤",
                        "estimated_minutes": 30,
                        "dependency_keys": [],
                        "acceptance_criteria": ["完成"],
                    }
                ],
            },
            "plan": {"blocks": [], "unscheduled": []},
        }

        async def seed():
            async with c.app.state.sessions() as db:
                draft = await imports.create_draft(db, owner, kind, payloads[kind])
                await db.commit()
                return draft

        draft = c.portal.call(seed)
        url = f"/api/drafts/{draft['id']}"
        assert delete(c, h, url, 2, "stale").status_code == 409
        assert len(c.get("/api/drafts").json()) == 1
        result = delete(c, h, url, 1)
        assert result.status_code == 200
        assert delete(c, h, url, 1).json() == result.json()
        assert c.get("/api/drafts").json() == []
        assert c.get(url).json()["data"]["status"] == "deleted"
        assert (
            post(c, h, url + "/confirm", {"revision": 1}, "confirm").status_code == 409
        )
        assert (
            c.put(
                url,
                json={"revision": 2, "payload": payloads[kind]},
                headers={**h, "Idempotency-Key": "edit"},
            ).status_code
            == 409
        )
        assert c.get(f"/api/tasks/{task['id']}").json() == task
        assert c.get("/api/fixed-events").json() == []
        assert (
            delete(c, h, f"/api/drafts/{confirmed['id']}", 2, "confirmed").status_code
            == 409
        )


def test_deletion_requires_auth_csrf_and_owner(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, _ = assignment(c, h)
        draft = post(
            c, h, "/api/drafts/assignment", {"items": [{"title": "草稿"}]}, "draft"
        ).json()
        urls = [f"/api/tasks/{task['id']}", f"/api/drafts/{draft['id']}"]
        for url in urls:
            assert delete(c, {}, url, 1).status_code == 403
        c.post("/api/auth/logout", headers=h)
        for url in urls:
            assert delete(c, h, url, 1).status_code == 401
        other = register_login(c, "other@example.com")
        for url in urls:
            assert delete(c, other, url, 1).status_code == 404


def test_delete_browser_draft_cancels_import_and_rejects_late_capture(tmp_path):
    with configured_client(tmp_path) as c:
        h = register_login(c)
        session = post(
            c, h, "/api/browser-imports", {"school_id": "scut"}, "start"
        ).json()
        url = f"/api/browser-imports/{session['id']}"
        for kind in ["opened", "waiting_timetable", "extracting"]:
            session = post(
                c,
                h,
                url + "/events",
                {"kind": kind, "event_id": kind, "revision": session["revision"]},
                kind,
            ).json()
        capture = {
            "revision": session["revision"],
            "adapter_version": "test-fixture-v1",
            "school_origin": "https://fixture.scut.edu.cn",
            "semester_label": "测试学期",
            "fragments": [
                "<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th></tr><tr><td>测试数学</td><td>1</td><td>1-8</td><td>1-2</td><td>A101</td></tr></table>"
            ],
        }
        draft = post(c, h, url + "/capture", capture, "capture").json()
        assert (
            delete(c, h, f"/api/drafts/{draft['id']}", draft["revision"]).status_code
            == 200
        )
        assert c.get(url).json()["data"]["status"] == "cancelled"
        assert post(c, h, url + "/capture", capture, "late").status_code == 409
        assert c.get("/api/drafts").json() == []
        assert c.get("/api/courses").json() == []


def test_delete_receipts_and_tombstones_survive_restart(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        cookies = dict(c.cookies)
        task, _ = assignment(c, h)
        draft = post(
            c, h, "/api/drafts/assignment", {"items": [{"title": "待丢弃"}]}, "pending"
        ).json()
        task_url, draft_url = f"/api/tasks/{task['id']}", f"/api/drafts/{draft['id']}"
        task_result = delete(c, h, task_url, task["revision"]).json()
        draft_result = delete(c, h, draft_url, draft["revision"]).json()
        assert task_result["deleted"] and draft_result["deleted"]
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        assert delete(c, h, task_url, task["revision"]).json() == task_result
        assert delete(c, h, draft_url, draft["revision"]).json() == draft_result
        assert c.get("/api/tasks").json() == []
        assert c.get("/api/drafts").json() == []
        assert (
            post(c, h, draft_url + "/confirm", {"revision": 1}, "late").status_code
            == 409
        )


def test_old_agent_approval_cannot_save_deleted_draft(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: ToolModel()
        draft = post(
            c,
            h,
            "/api/drafts/assignment",
            {"items": [{"title": "不会被旧批准保存"}]},
            "pending",
        ).json()
        thread = post(c, h, "/api/agent/threads", {}, "thread").json()
        run = post(
            c,
            h,
            "/api/agent/runs",
            {"thread_id": thread["id"], "message": "commit:" + draft["id"]},
            "run",
        ).json()
        pending = wait_run(c, run["id"])
        assert pending["data"]["status"] == "waiting_approval"
        approval = c.get(
            "/api/agent/approvals/" + pending["data"]["approval_id"]
        ).json()
        assert (
            delete(c, h, f"/api/drafts/{draft['id']}", draft["revision"]).status_code
            == 200
        )
        assert (
            post(
                c,
                h,
                f"/api/agent/runs/{run['id']}/resume",
                {
                    "approval_id": approval["id"],
                    "revision": approval["revision"],
                    "decision": "approve",
                },
                "stale-approval",
            ).status_code
            == 200
        )
        assert wait_run(c, run["id"])["data"]["status"] == "failed"
        assert c.get("/api/tasks").json() == []
        assert c.get("/api/drafts").json() == []
