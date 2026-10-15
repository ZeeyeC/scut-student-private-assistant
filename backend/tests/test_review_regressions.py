from datetime import timedelta

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ValidationError

from app.browser_imports import parse_capture
from app.contracts import StepUpdate, StudentSettings, TaskUpdate
from app.db import now
from app.model_gateway import normalize_extraction
from tests.test_agent import ToolModel, wait_run
from tests.test_browser_import import configured_client
from tests.test_foundation import make_client, register_login
from tests.test_steps import task_and_headers


class SequentialWrites(ToolModel):
    task_ids: list[str]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        count = sum(isinstance(m, ToolMessage) for m in messages)
        message = (
            AIMessage(content="完成")
            if count >= 2
            else AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "set_task_status",
                        "args": {
                            "task_id": self.task_ids[count],
                            "revision": 1,
                            "status": "completed",
                        },
                        "id": f"write-{count}",
                        "type": "tool_call",
                    }
                ],
            )
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def confirm(c, h, draft, key):
    r = c.post(
        f"/api/drafts/{draft['id']}/confirm",
        json={"revision": draft["revision"]},
        headers={**h, "Idempotency-Key": key},
    )
    assert r.status_code == 200, r.text


def step_draft(c, h, task, key):
    r = c.post(
        f"/api/tasks/{task['id']}/step-drafts",
        json={
            "task_revision": task["revision"],
            "steps": [
                {
                    "key": "a",
                    "title": "阅读",
                    "description": "阅读指定材料",
                    "estimated_minutes": 30,
                    "dependency_keys": [],
                    "acceptance_criteria": ["写出摘要"],
                }
            ],
        },
        headers={**h, "Idempotency-Key": key},
    )
    assert r.status_code == 200, r.text
    confirm(c, h, r.json(), key + "-save")


def test_second_write_requires_a_new_approval(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = c.post(
            "/api/drafts/assignment",
            json={
                "items": [
                    {"title": "A", "requirements": []},
                    {"title": "B", "requirements": []},
                ]
            },
            headers={**h, "Idempotency-Key": "draft"},
        ).json()
        confirm(c, h, d, "save")
        ids = [t["id"] for t in c.get("/api/tasks").json()]
        c.app.state.agent_model_factory = lambda: SequentialWrites(task_ids=ids)
        thread = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "thread"}
        ).json()
        run = c.post(
            "/api/agent/runs",
            json={"thread_id": thread["id"], "message": "完成两项"},
            headers={**h, "Idempotency-Key": "run"},
        ).json()
        old = None
        for i in range(2):
            run = wait_run(c, run["id"])
            assert run["data"]["status"] == "waiting_approval"
            aid = run["data"]["approval_id"]
            assert aid != old
            assert c.get(f"/api/tasks/{ids[i]}").json()["data"]["status"] == "open"
            a = c.get("/api/agent/approvals/" + aid).json()
            r = c.post(
                f"/api/agent/runs/{run['id']}/resume",
                json={
                    "approval_id": aid,
                    "revision": a["revision"],
                    "decision": "approve",
                },
                headers={**h, "Idempotency-Key": f"approve-{i}"},
            )
            assert r.status_code == 200, r.text
            old = aid
        assert wait_run(c, run["id"])["data"]["status"] == "done"
        assert all(
            t["data"]["status"] == "completed" for t in c.get("/api/tasks").json()
        )


def test_other_horizon_allocations_are_counted_and_redecomposition_cleans_blocks(
    tmp_path,
):
    with make_client(tmp_path) as c:
        task, h = task_and_headers(c)
        step_draft(c, h, task, "steps")
        for offset in (2, 1):
            d = c.post(
                "/api/plan-drafts",
                json={
                    "target_date": (now() + timedelta(days=offset)).date().isoformat(),
                    "horizon_days": 1,
                },
                headers={**h, "Idempotency-Key": f"plan-{offset}"},
            ).json()
            confirm(c, h, d, f"save-plan-{offset}")
        blocks = c.get("/api/plan-blocks").json()
        assert len(blocks) == 1, "one 30 minute step must not be allocated twice"
        task = c.get("/api/tasks/" + task["id"]).json()
        step_draft(c, h, task, "replace-steps")
        assert c.get("/api/plan-blocks").json() == []


def test_missing_year_or_evidence_keeps_deadline_uncertain():
    for text in ("10月20日18:00", None):
        r = normalize_extraction(
            {
                "items": [
                    {
                        "title": "报告",
                        "due_text": text,
                        "due_at": "2026-10-20T18:00:00+08:00",
                    }
                ]
            },
            [],
            None,
        )
        assert r["items"][0]["due_at"] is None
        assert "due_at" in r["items"][0]["uncertain_fields"]


def test_split_week_meetings_and_no_static_full_deletion():
    adapter = {
        "columns": {
            "name": "课程",
            "weekday": "星期",
            "weeks": "周次",
            "periods": "节次",
            "location": "地点",
        },
        "full_capture": True,
    }
    fragment = (
        "<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th></tr>"
        + "".join(
            f"<tr><td>数学</td><td>1</td><td>{weeks}</td><td>1-2</td><td>{room}</td></tr>"
            for weeks, room in [("1-8", "A101"), ("9-16", "B201")]
        )
        + "</table>"
    )
    r = parse_capture([fragment], adapter, 20)
    assert len({c["source_key"] for c in r["courses"]}) == 2
    assert r["completeness"] == "partial"


def test_invalid_timezone_and_null_required_patch_fields_are_validation_errors():
    with pytest.raises(ValidationError):
        StudentSettings(timezone="Invalid/Zone")
    for field in ("spent_minutes", "estimated_minutes", "title", "status"):
        with pytest.raises(ValidationError):
            StepUpdate.model_validate({"revision": 1, field: None})
    for field in ("title", "status", "priority"):
        with pytest.raises(ValidationError):
            TaskUpdate.model_validate({"revision": 1, field: None})
    assert TaskUpdate(revision=1, due_at=None).due_at is None


def test_crash_between_checkpoint_interrupt_and_approval_publication_recovers(tmp_path):
    from sqlalchemy import select

    from app.db import Resource

    with make_client(tmp_path) as c:
        h = register_login(c)
        cookies = dict(c.cookies)
        c.app.state.agent_model_factory = lambda: ToolModel()
        d = c.post(
            "/api/drafts/assignment",
            json={"items": [{"title": "报告"}]},
            headers={**h, "Idempotency-Key": "draft"},
        ).json()
        thread = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "thread"}
        ).json()
        r = c.post(
            "/api/agent/runs",
            json={"thread_id": thread["id"], "message": "commit:" + d["id"]},
            headers={**h, "Idempotency-Key": "run"},
        ).json()
        r = wait_run(c, r["id"])

        async def simulate_crash_window():
            async with c.app.state.sessions() as db:
                run = await db.get(Resource, r["id"])
                a = await db.get(Resource, run.data["approval_id"])
                await db.delete(a)
                for event in await db.scalars(
                    select(Resource).where(Resource.kind == "agent_event")
                ):
                    if (
                        event.data["run_id"] == r["id"]
                        and event.data["type"] == "approval_required"
                    ):
                        await db.delete(event)
                run.data = {**run.data, "status": "running", "approval_id": None}
                await db.commit()

        c.portal.call(simulate_crash_window)
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        c.app.state.agent_model_factory = lambda: ToolModel()
        r = c.get("/api/agent/runs/" + r["id"]).json()
        assert r["data"]["status"] == "waiting_approval"
        assert c.get("/api/tasks").json() == []
        a = c.get("/api/agent/approvals/" + r["data"]["approval_id"]).json()
        res = c.post(
            f"/api/agent/runs/{r['id']}/resume",
            json={
                "approval_id": a["id"],
                "revision": a["revision"],
                "decision": "approve",
            },
            headers={**h, "Idempotency-Key": "resume"},
        )
        assert res.status_code == 200, res.text
        assert wait_run(c, r["id"])["data"]["status"] == "done"
        assert len(c.get("/api/tasks").json()) == 1


@pytest.mark.parametrize("terminal", ["cancelled", "expired"])
def test_browser_preview_termination_prevents_saving(tmp_path, terminal):
    from app.db import Resource

    with configured_client(tmp_path) as c:
        h = register_login(c)
        b = c.post(
            "/api/browser-imports", json={}, headers={**h, "Idempotency-Key": "b"}
        ).json()
        url = "/api/browser-imports/" + b["id"]
        for kind in ("opened", "waiting_timetable", "extracting"):
            b = c.post(
                url + "/events",
                json={"revision": b["revision"], "event_id": kind, "kind": kind},
                headers={**h, "Idempotency-Key": kind},
            ).json()
        d = c.post(
            url + "/capture",
            json={
                "revision": b["revision"],
                "adapter_version": "test-fixture-v1",
                "school_origin": "https://fixture.scut.edu.cn",
                "semester_label": "测试",
                "fragments": [
                    "<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th></tr><tr><td>数学</td><td>1</td><td>1-8</td><td>1-2</td><td>A101</td></tr></table>"
                ],
            },
            headers={**h, "Idempotency-Key": "capture"},
        ).json()
        if terminal == "cancelled":
            b = c.get(url).json()
            assert (
                c.post(
                    url + "/cancel",
                    json={"revision": b["revision"]},
                    headers={**h, "Idempotency-Key": "cancel"},
                ).status_code
                == 200
            )
        else:

            async def expire():
                async with c.app.state.sessions() as db:
                    row = await db.get(Resource, b["id"])
                    row.data = {
                        **row.data,
                        "expires_at": (now() - timedelta(seconds=1)).isoformat(),
                    }
                    await db.commit()

            c.portal.call(expire)
        r = c.post(
            f"/api/drafts/{d['id']}/confirm",
            json={"revision": 1},
            headers={**h, "Idempotency-Key": "save"},
        )
        assert r.status_code == 409
        assert c.get("/api/courses").json() == []


def test_only_fixed_observed_scut_http_route_can_pass_url_validation(tmp_path):
    import json
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.browser_imports import load_adapter

    path = tmp_path / "test-url-validation.json"
    # Test the URL gate only: this is not a real DOM verification configuration.
    config = {
        "verified": True,
        "entry_url": "http://xsjw2018.jw.scut.edu.cn/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151&layout=default",
        "school_origin": "http://xsjw2018.jw.scut.edu.cn",
    }
    path.write_text(json.dumps(config))
    assert (
        load_adapter(SimpleNamespace(scut_adapter_path=str(path)))["entry_url"]
        == config["entry_url"]
    )
    config["entry_url"] += "&token=must-not-be-accepted"
    path.write_text(json.dumps(config))
    with pytest.raises(HTTPException):
        load_adapter(SimpleNamespace(scut_adapter_path=str(path)))


@pytest.mark.parametrize("concurrent_change", [False, True])
def test_slow_model_decomposition_does_not_lock_student_database(
    tmp_path, concurrent_change
):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    started, release = threading.Event(), threading.Event()

    class SlowGateway:
        calls = 0

        async def decompose_task(self, *args):
            self.calls += 1
            started.set()
            await asyncio.to_thread(release.wait)
            return {
                "steps": [
                    {
                        "key": "a",
                        "title": "阅读",
                        "description": "阅读材料",
                        "estimated_minutes": 30,
                        "dependency_keys": [],
                        "acceptance_criteria": ["摘要"],
                    }
                ]
            }

    with make_client(tmp_path) as c, ThreadPoolExecutor(2) as pool:
        task, h = task_and_headers(c)
        if concurrent_change:
            step_draft(c, h, task, "initial-steps")
        c.app.state.gateway = SlowGateway()
        headers = {**h, "Idempotency-Key": "decompose"}
        url = "/api/tasks/" + task["id"] + "/decompose"
        work = pool.submit(c.post, url, json={"consent": True}, headers=headers)
        assert started.wait(2)
        try:
            read = pool.submit(c.get, "/api/settings")
            assert read.result(timeout=2).status_code == 200
            if concurrent_change:
                step = c.get("/api/tasks/" + task["id"] + "/steps").json()[0]
                response = c.patch(
                    "/api/steps/" + step["id"],
                    json={"revision": step["revision"], "status": "completed"},
                    headers={**h, "Idempotency-Key": "step-done"},
                )
                assert response.status_code == 200
        finally:
            release.set()
        result = work.result(timeout=3)
        if concurrent_change:
            assert result.status_code == 409, result.text
            return
        assert result.status_code == 200, result.text
        assert (
            c.post(url, json={"consent": True}, headers=headers).json()["id"]
            == result.json()["id"]
        )
        assert c.app.state.gateway.calls == 1


def test_measured_scut_profile_and_high_week_normalized_table():
    from pathlib import Path
    from types import SimpleNamespace

    from app.browser_imports import load_adapter

    path = (
        Path(__file__).resolve().parents[2]
        / "config/scut-undergraduate-2026-10-14.json"
    )
    adapter = load_adapter(SimpleNamespace(scut_adapter_path=str(path)))
    assert adapter["entry_url"] == "http://xsjw2018.jw.scut.edu.cn/"
    fragment = "<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th><th>教师</th><th>校区</th><th>教学班</th></tr><tr><td>虚构测试数学</td><td>4</td><td>1-16周,21-22周</td><td>9-12</td><td>测试室</td><td>测试教师</td><td>大学城校区</td><td>test-class</td></tr></table>"
    result = parse_capture([fragment], adapter, 30)
    course = result["courses"][0]
    assert course["weeks"] == list(range(1, 17)) + [21, 22]
    assert course["periods"] == [9, 10, 11, 12]
    assert course["teacher"] == "测试教师"
    assert result["completeness"] == "partial"


def test_expired_approval_cannot_write_but_can_be_rejected(tmp_path):
    from app.db import Resource

    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: ToolModel()
        d = c.post(
            "/api/drafts/assignment",
            json={"items": [{"title": "测试作业"}]},
            headers={**h, "Idempotency-Key": "draft"},
        ).json()
        t = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "thread"}
        ).json()
        r = c.post(
            "/api/agent/runs",
            json={"thread_id": t["id"], "message": "commit:" + d["id"]},
            headers={**h, "Idempotency-Key": "run"},
        ).json()
        r = wait_run(c, r["id"])
        aid = r["data"]["approval_id"]

        async def expire():
            async with c.app.state.sessions() as db:
                a = await db.get(Resource, aid)
                a.data = {
                    **a.data,
                    "expires_at": (now() - timedelta(seconds=1)).isoformat(),
                }
                await db.commit()

        c.portal.call(expire)
        a = c.get("/api/agent/approvals/" + aid).json()
        for decision, status in [("approve", 409), ("reject", 200)]:
            response = c.post(
                "/api/agent/runs/" + r["id"] + "/resume",
                json={
                    "approval_id": aid,
                    "revision": a["revision"],
                    "decision": decision,
                },
                headers={**h, "Idempotency-Key": decision},
            )
            assert response.status_code == status, response.text
        assert wait_run(c, r["id"])["data"]["status"] == "done"
        assert c.get("/api/tasks").json() == []
        assert (
            c.post(
                "/api/agent/runs",
                json={"thread_id": t["id"], "message": "查询"},
                headers={**h, "Idempotency-Key": "next"},
            ).status_code
            == 200
        )


def test_changed_deadline_replans_invalid_outside_horizon_block(tmp_path):
    with make_client(tmp_path) as c:
        task, h = task_and_headers(c)
        step_draft(c, h, task, "steps")
        target = (now() + timedelta(days=2)).date().isoformat()
        d = c.post(
            "/api/plan-drafts",
            json={"target_date": target, "horizon_days": 1},
            headers={**h, "Idempotency-Key": "later"},
        ).json()
        confirm(c, h, d, "later-save")
        old = c.get("/api/plan-blocks").json()[0]
        task = c.get("/api/tasks/" + task["id"]).json()
        c.patch(
            "/api/tasks/" + task["id"],
            json={
                "revision": task["revision"],
                "due_at": (now() + timedelta(days=1)).isoformat(),
            },
            headers={**h, "Idempotency-Key": "deadline"},
        )
        d = c.post(
            "/api/plan-drafts",
            json={
                "target_date": (now() + timedelta(days=1)).date().isoformat(),
                "horizon_days": 1,
            },
            headers={**h, "Idempotency-Key": "earlier"},
        ).json()
        p = d["data"]["payload"]
        assert all(b["id"] != old["id"] for b in p["blocks"])
        assert p["warnings"]
        assert p["removed_blocks"][0]["id"] == old["id"]
        confirm(c, h, d, "earlier-save")
        assert all(b["id"] != old["id"] for b in c.get("/api/plan-blocks").json())
