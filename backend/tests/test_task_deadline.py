import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent import student_agent
from tests.test_agent import ToolModel, wait_run
from tests.test_calendar_events import post
from tests.test_deletion import assignment
from tests.test_foundation import make_client, register_login


@pytest.fixture(autouse=True)
def test_only_clock(monkeypatch):
    async def clock(timezone):
        return {
            "source": "test-only-clock",
            "timezone": timezone,
            "datetime": "2026-10-15T12:00:00+08:00",
            "today": "2026-10-15",
            "tomorrow": "2026-10-16",
            "yesterday": "2026-10-14",
        }

    monkeypatch.setattr("app.time_mcp.current_time", clock)


class DeadlineModel(ToolModel):
    """Test-only natural-language deadline flow using actual graph tools/HITL."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1]
        if isinstance(last, ToolMessage) and last.name == "set_task_deadline":
            message = AIMessage(
                content="已按确认更新截止时间；已有学习安排请重新规划。"
            )
        elif isinstance(last, ToolMessage) and last.name == "get_current_time":
            message = self.call("list_tasks", {"status": "open"})
        elif isinstance(last, ToolMessage) and last.name == "list_tasks":
            tasks = json.loads(last.content)
            task = next(t for t in tasks if t["data"]["title"] == "截止测试报告")
            text = next(
                str(m.content)
                for m in reversed(messages)
                if isinstance(m, HumanMessage)
            )
            if "没有几点" in text:
                message = AIMessage(content="请补充明确的截止钟点，例如明天晚上8点。")
            else:
                clock = next(
                    json.loads(m.content)
                    for m in reversed(messages)
                    if isinstance(m, ToolMessage) and m.name == "get_current_time"
                )
                message = self.call(
                    "set_task_deadline",
                    {
                        "task_id": task["id"],
                        "revision": task["revision"],
                        "due_at": clock["tomorrow"] + "T20:00:00+08:00",
                        "deadline_type": "remedy_due_at"
                        if "补救" in text
                        else "due_at",
                    },
                )
        else:
            message = self.call("get_current_time", {})
        return ChatResult(generations=[ChatGeneration(message=message)])

    def call(self, name, args):
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": name, "type": "tool_call"}],
        )


def propose(c, h, message="把截止测试报告的截止时间改为明天晚上8点"):
    c.app.state.agent_model_factory = lambda: DeadlineModel()
    thread = post(c, h, "/api/agent/threads", {}, "thread").json()
    run = post(
        c, h, "/api/agent/runs", {"thread_id": thread["id"], "message": message}, "run"
    ).json()
    pending = wait_run(c, run["id"])
    assert pending["data"]["status"] == "waiting_approval"
    approval = c.get("/api/agent/approvals/" + pending["data"]["approval_id"]).json()
    return pending, approval


def decision(c, h, run, approval, value="approve", key="approve"):
    result = post(
        c,
        h,
        f"/api/agent/runs/{run['id']}/resume",
        {
            "approval_id": approval["id"],
            "revision": approval["revision"],
            "decision": value,
        },
        key,
    )
    assert result.status_code == 200
    return wait_run(c, run["id"])


def test_natural_deadline_requires_approval_and_survives_restart_and_replay(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        cookies = dict(c.cookies)
        task, _ = assignment(c, h, "截止测试报告")
        plan = post(c, h, "/api/plan-drafts", {}, "plan").json()
        run, approval = propose(c, h)
        assert approval["data"]["actions"][0]["name"] == "set_task_deadline"
        expected = approval["data"]["actions"][0]["args"]["due_at"]
        assert c.get(f"/api/tasks/{task['id']}").json() == task
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        c.app.state.agent_model_factory = lambda: DeadlineModel()
        assert decision(c, h, run, approval)["data"]["status"] == "done"
        updated = c.get(f"/api/tasks/{task['id']}").json()
        assert updated["data"]["due_at"] == expected
        assert "due_at" not in updated["data"]["uncertain_fields"]
        assert updated["revision"] == task["revision"] + 1
        assert len(c.get("/api/tasks").json()) == 1
        assert (
            c.get(f"/api/drafts/{plan['id']}").json()["data"]["status"] == "superseded"
        )
        for key in ["approve", "approve-again"]:
            decision(c, h, run, approval, key=key)
        assert c.get(f"/api/tasks/{task['id']}").json() == updated


@pytest.mark.parametrize("mode", ["reject", "stale", "deleted"])
def test_deadline_reject_stale_or_deleted_never_overwrites_task(tmp_path, mode):
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, _ = assignment(c, h, "截止测试报告")
        run, approval = propose(c, h)
        if mode == "stale":
            assert (
                c.patch(
                    f"/api/tasks/{task['id']}",
                    json={"revision": task["revision"], "title": "新版本标题"},
                    headers={**h, "Idempotency-Key": "change"},
                ).status_code
                == 200
            )
        elif mode == "deleted":
            assert (
                c.request(
                    "DELETE",
                    f"/api/tasks/{task['id']}",
                    json={"revision": task["revision"]},
                    headers={**h, "Idempotency-Key": "delete"},
                ).status_code
                == 200
            )
        result = decision(
            c, h, run, approval, "reject" if mode == "reject" else "approve"
        )
        assert result["data"]["status"] == ("done" if mode == "reject" else "failed")
        if mode == "deleted":
            assert c.get("/api/tasks").json() == []
        else:
            assert c.get(f"/api/tasks/{task['id']}").json()["data"]["due_at"] is None


@pytest.mark.asyncio
async def test_deadline_tool_requires_server_capability_and_validates_owner_and_time(
    tmp_path,
):
    # The actual installed graph tool must not turn model arguments into authority.
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, _ = assignment(c, h, "截止测试报告")
        owner = c.get("/api/me").json()["id"]
        c.app.state.agent_model_factory = lambda: DeadlineModel()
        graph = student_agent(c.app, owner)
        tool = graph.nodes["tools"].bound.tools_by_name["set_task_deadline"]
        with pytest.raises(ValueError, match="确认"):
            await tool.ainvoke(
                {
                    "task_id": task["id"],
                    "due_at": "2026-10-16T20:00:00+08:00",
                    "revision": task["revision"],
                    "deadline_type": "due_at",
                }
            )
        with pytest.raises(ValueError, match="时区"):
            await tool.ainvoke(
                {
                    "task_id": task["id"],
                    "due_at": "2026-10-16T20:00:00",
                    "revision": task["revision"],
                    "deadline_type": "due_at",
                }
            )
        # Domain updates use the same authenticated, versioned service as manual edits.
        from app.contracts import TaskUpdate
        from app.tasks import apply_task_update

        async with c.app.state.sessions() as db:
            with pytest.raises(HTTPException) as exc:
                await apply_task_update(
                    db,
                    "another-owner",
                    task["id"],
                    TaskUpdate(revision=1, due_at="2026-10-16T20:00:00+08:00"),
                )
            assert exc.value.status_code == 404
        assert c.get(f"/api/tasks/{task['id']}").json() == task


def test_explicit_deadline_clears_old_remedy_and_preserves_steps_and_blocks(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, _ = assignment(c, h, "截止测试报告")
        owner = c.get("/api/me").json()["id"]

        async def seed():
            from app.db import Resource

            async with c.app.state.sessions() as db:
                for rid, kind, data in [
                    ("step", "step", {"task_id": task["id"], "title": "保留步骤"}),
                    (
                        "locked",
                        "plan_block",
                        {"task_id": task["id"], "step_id": "step", "locked": True},
                    ),
                ]:
                    db.add(Resource(id=rid, owner_id=owner, kind=kind, data=data))
                await db.commit()

        c.portal.call(seed)
        old_remedy = (
            datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=3)
        ).isoformat()
        assert (
            c.patch(
                f"/api/tasks/{task['id']}",
                json={"revision": task["revision"], "remedy_due_at": old_remedy},
                headers={**h, "Idempotency-Key": "remedy"},
            ).status_code
            == 200
        )
        run, approval = propose(c, h)
        assert decision(c, h, run, approval)["data"]["status"] == "done"
        data = c.get(f"/api/tasks/{task['id']}").json()["data"]
        assert data["due_at"] is not None and data["remedy_due_at"] is None
        assert c.get(f"/api/tasks/{task['id']}/steps").json()[0]["id"] == "step"
        assert c.get("/api/plan-blocks").json()[0]["data"]["locked"] is True


def test_relative_date_without_clock_only_asks_for_clarification(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, _ = assignment(c, h, "截止测试报告")
        c.app.state.agent_model_factory = lambda: DeadlineModel()
        thread = post(c, h, "/api/agent/threads", {}, "thread").json()
        run = post(
            c,
            h,
            "/api/agent/runs",
            {"thread_id": thread["id"], "message": "截止改为明天，没有几点"},
            "run",
        ).json()
        assert wait_run(c, run["id"])["data"]["status"] == "done"
        assert c.get(f"/api/tasks/{task['id']}").json() == task


def test_explicit_recovery_deadline_keeps_original_overdue_date(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        task, _ = assignment(c, h, "截止测试报告")
        original_due = "2026-10-10T20:00:00+08:00"
        response = c.patch(
            f"/api/tasks/{task['id']}",
            json={"revision": task["revision"], "due_at": original_due},
            headers={**h, "Idempotency-Key": "past"},
        )
        assert response.status_code == 200
        run, approval = propose(c, h, "把截止测试报告的补救截止时间改为明天晚上8点")
        assert decision(c, h, run, approval)["data"]["status"] == "done"
        updated = c.get(f"/api/tasks/{task['id']}").json()
        assert updated["data"]["due_at"] == original_due
        assert updated["data"]["remedy_due_at"] == "2026-10-16T20:00:00+08:00"
