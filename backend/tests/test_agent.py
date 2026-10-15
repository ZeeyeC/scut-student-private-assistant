import time

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tests.test_foundation import make_client, register_login


class ToolModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "test-only-business-tools"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content="业务工具执行完毕"))
                ]
            )
        text = str(messages[-1].content)
        if text.startswith("commit:"):
            tool = {
                "name": "commit_import",
                "args": {"draft_id": text.split(":", 1)[1], "revision": 1},
                "id": "commit-1",
                "type": "tool_call",
            }
        else:
            tool = {
                "name": "list_tasks",
                "args": {"status": "open"},
                "id": "list-1",
                "type": "tool_call",
            }
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content="", tool_calls=[tool]))
            ]
        )


def wait_run(c, rid):
    for _ in range(100):
        r = c.get("/api/agent/runs/" + rid)
        if r.status_code == 200 and r.json()["data"]["status"] in (
            "waiting_approval",
            "done",
            "failed",
        ):
            return r.json()
        time.sleep(0.03)
    raise AssertionError("run did not reach terminal/pending state")


def test_actual_tools_restricted_and_real_service_query(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: ToolModel()
        thread = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "thread"}
        ).json()
        r = c.post(
            "/api/agent/runs",
            json={"thread_id": thread["id"], "message": "查询作业"},
            headers={**h, "Idempotency-Key": "run"},
        )
        assert r.status_code == 200
        r = wait_run(c, r.json()["id"])
        assert r["data"]["status"] == "done"
        events = c.get("/api/agent/runs/" + r["id"] + "/events?after=0").text
        assert "list_tasks" in events
        assert "业务工具执行完毕" in events
        assert c.get("/api/tasks").json() == []
        assert c.get("/api/agent/tools").json()["tools"] == sorted(
            [
                "get_current_time",
                "get_student_context",
                "start_timetable_import",
                "get_timetable_import_status",
                "list_course_occurrences",
                "list_tasks",
                "create_assignment_draft",
                "list_assignment_drafts",
                "set_assignment_draft_deadline",
                "resolve_academic_deadline",
                "create_calendar_event_draft",
                "list_calendar_events",
                "propose_decomposition",
                "propose_daily_plan",
                "commit_import",
                "commit_plan",
                "set_task_status",
                "set_task_deadline",
            ]
        )


def test_pending_approval_reboot_replay_and_owner(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        cookies = dict(c.cookies)
        c.app.state.agent_model_factory = lambda: ToolModel()
        d = c.post(
            "/api/drafts/assignment",
            json={"items": [{"title": "报告", "requirements": []}]},
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
        assert r["data"]["status"] == "waiting_approval"
        assert c.get("/api/tasks").json() == []
        aid = r["data"]["approval_id"]
        approval = c.get("/api/agent/approvals/" + aid).json()
        assert (
            c.post(
                "/api/agent/runs",
                json={"thread_id": t["id"], "message": "查询"},
                headers={**h, "Idempotency-Key": "parallel"},
            ).status_code
            == 409
        )
    from app.backup import backup, restore

    package = tmp_path / "pending.zip"
    backup(tmp_path / "test.db", tmp_path / "agent.db", tmp_path / "uploads", package)
    restored = tmp_path / "restored"
    restore(package, restored)
    (restored / "campus.db").rename(restored / "test.db")
    with make_client(restored) as c:
        c.cookies.update(cookies)
        c.app.state.agent_model_factory = lambda: ToolModel()
        decision = {
            "approval_id": aid,
            "revision": approval["revision"],
            "decision": "approve",
        }
        for key in ["approve", "approve-again"]:
            assert (
                c.post(
                    "/api/agent/runs/" + r["id"] + "/resume",
                    json=decision,
                    headers={**h, "Idempotency-Key": key},
                ).status_code
                == 200
            )
            wait_run(c, r["id"])
        assert len(c.get("/api/tasks").json()) == 1
        events = c.get("/api/agent/runs/" + r["id"] + "/events?after=99999").text
        assert events == ""
        c.post("/api/auth/logout", headers=h)
        register_login(c, "bob@example.com")
        assert c.get("/api/agent/runs/" + r["id"]).status_code == 404
        assert c.get("/api/agent/approvals/" + aid).status_code == 404
