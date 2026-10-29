"""Business tools and approvals use real domain services, no online model."""

import json
from datetime import datetime

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import write


def post(c, h, path, body):
    r = write(c, h, path, body)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_constraint_tools_recover_and_do_not_save_without_confirmation(
    tmp_path, monkeypatch
):
    from app import conversation_constraints
    from app.agent import conversation, student_agent

    monkeypatch.setattr(
        conversation_constraints,
        "now",
        lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00"),
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        owner = c.get("/api/me").json()["id"]
        thread = post(c, h, "/agent/threads", {})
        c.app.state.agent_model_factory = lambda: ToolModel()

        async def calls():
            graph = student_agent(c.app, owner)
            tools = graph.nodes["tools"].bound.tools_by_name
            assert {
                "propose_constraint_intent",
                "update_constraint_intent",
                "prepare_constraint_intent",
                "list_constraint_intents",
                "get_planning_context",
                "propose_planning_intent",
                "update_planning_intent",
                "preview_planning_intent",
            } <= set(tools)
            token = conversation.set(
                {
                    "run_id": "isolated-conversation-probe",
                    "thread_id": thread["id"],
                    "message_at": "2026-10-14T00:00:00+00:00",
                    "message": "这周三下午别排事",
                }
            )
            try:
                body = {"day_expression": "这周三下午"}
                first = await tools["propose_constraint_intent"].ainvoke(body)
                assert first == await tools["propose_constraint_intent"].ainvoke(body)
                changed = await tools["update_constraint_intent"].ainvoke(
                    {
                        "intent_id": first["id"],
                        "revision": first["revision"],
                        "changes": {"start_time": "14:00", "end_time": "17:00"},
                    }
                )
                ready = await tools["prepare_constraint_intent"].ainvoke(
                    {"intent_id": changed["id"], "revision": changed["revision"]}
                )
                assert (
                    ready["id"] == first["id"]
                    and ready["draft"]["data"]["draft_kind"] == "scheduling_constraint"
                )
            finally:
                conversation.reset(token)

        c.portal.call(calls)
        assert c.get("/api/scheduling-constraints").json() == []


def test_chat_calendar_approval_requires_current_conflict_review_token(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: ToolModel()
        draft = post(
            c,
            h,
            "/drafts/calendar-event",
            {
                "title": "合成会议",
                "starts_at": "2026-10-14T10:00:00+08:00",
                "ends_at": "2026-10-14T11:00:00+08:00",
            },
        )
        thread = post(c, h, "/agent/threads", {})
        run = wait_run(
            c,
            post(
                c,
                h,
                "/agent/runs",
                {"thread_id": thread["id"], "message": "commit:" + draft["id"]},
            )["id"],
        )
        aid = run["data"]["approval_id"]
        approval = c.get("/api/agent/approvals/" + aid).json()
        body = {
            "approval_id": aid,
            "revision": approval["revision"],
            "decision": "approve",
        }
        assert write(c, h, f"/agent/runs/{run['id']}/resume", body).status_code == 409
        assert c.get("/api/fixed-events").json() == []
        review = post(
            c,
            h,
            f"/drafts/{draft['id']}/conflict-preview",
            {"revision": draft["revision"], "payload": draft["data"]["payload"]},
        )
        accepted = post(
            c,
            h,
            f"/agent/runs/{run['id']}/resume",
            {
                **body,
                "conflict_tokens": {draft["id"]: review["conflict_token"]},
                "conflict_acknowledged": [draft["id"]],
            },
        )
        assert wait_run(c, accepted["id"])["data"]["status"] == "done"
        assert len(c.get("/api/fixed-events").json()) == 1


def test_stale_conflict_token_and_unacknowledged_issue_reject_approval(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: ToolModel()
        values = {
            "title": "待确认合成事项",
            "starts_at": "2026-10-14T10:00:00+08:00",
            "ends_at": "2026-10-14T11:00:00+08:00",
        }
        d = post(c, h, "/drafts/calendar-event", values)
        old = post(
            c,
            h,
            f"/drafts/{d['id']}/conflict-preview",
            {"revision": d["revision"], "payload": d["data"]["payload"]},
        )
        other = post(
            c, h, "/drafts/calendar-event", {**values, "title": "已经确认的重叠事项"}
        )
        post(c, h, f"/drafts/{other['id']}/confirm", {"revision": other["revision"]})
        t = post(c, h, "/agent/threads", {})
        run = wait_run(
            c,
            post(
                c,
                h,
                "/agent/runs",
                {"thread_id": t["id"], "message": "commit:" + d["id"]},
            )["id"],
        )
        a = c.get("/api/agent/approvals/" + run["data"]["approval_id"]).json()
        body = {
            "approval_id": a["id"],
            "revision": a["revision"],
            "decision": "approve",
            "conflict_tokens": {d["id"]: old["conflict_token"]},
            "conflict_acknowledged": [d["id"]],
        }
        assert write(c, h, f"/agent/runs/{run['id']}/resume", body).status_code == 409
        fresh = post(
            c,
            h,
            f"/drafts/{d['id']}/conflict-preview",
            {"revision": d["revision"], "payload": d["data"]["payload"]},
        )
        assert fresh["conflict_count"] > 0
        assert (
            write(
                c,
                h,
                f"/agent/runs/{run['id']}/resume",
                {
                    **body,
                    "conflict_tokens": {d["id"]: fresh["conflict_token"]},
                    "conflict_acknowledged": [],
                },
            ).status_code
            == 409
        )
        assert len(c.get("/api/fixed-events").json()) == 1


class BatchModel(ToolModel):
    actions: list[dict]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            return super()._generate(messages, stop, run_manager, **kwargs)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {**action, "id": f"batch-{i}", "type": "tool_call"}
                            for i, action in enumerate(self.actions)
                        ],
                    )
                )
            ]
        )


@pytest.mark.parametrize("mode", ["two_facts", "task_first", "task_last"])
def test_conflict_fact_batch_is_rejected_before_any_write_and_remains_rejectable(
    tmp_path, mode
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        drafts = [
            post(
                c,
                h,
                "/drafts/calendar-event",
                {
                    "title": f"独立合成事项{i}",
                    "starts_at": f"2026-11-04T{hour}:00:00+08:00",
                    "ends_at": f"2026-11-04T{hour}:30:00+08:00",
                },
            )
            for i, hour in enumerate((10, 14))
        ]
        actions = [
            {
                "name": "commit_import",
                "args": {"draft_id": d["id"], "revision": d["revision"]},
            }
            for d in drafts
        ]
        if mode != "two_facts":
            td = post(
                c, h, "/drafts/assignment", {"items": [{"title": "合成批次任务"}]}
            )
            tid = post(
                c, h, f"/drafts/{td['id']}/confirm", {"revision": td["revision"]}
            )["saved_ids"][0]
            task = c.get("/api/tasks/" + tid).json()
            other = {
                "name": "set_task_status",
                "args": {
                    "task_id": tid,
                    "revision": task["revision"],
                    "status": "completed",
                },
            }
            actions = (
                [other, actions[0]] if mode == "task_first" else [actions[0], other]
            )
        before_tasks = c.get("/api/tasks").json()
        c.app.state.agent_model_factory = lambda: BatchModel(actions=actions)
        t = post(c, h, "/agent/threads", {})
        run = wait_run(
            c,
            post(
                c, h, "/agent/runs", {"thread_id": t["id"], "message": "合成批量批准"}
            )["id"],
        )
        assert run["data"]["status"] == "waiting_approval", json.dumps(run)
        approval = c.get("/api/agent/approvals/" + run["data"]["approval_id"]).json()
        tokens = {
            d["id"]: post(
                c,
                h,
                f"/drafts/{d['id']}/conflict-preview",
                {"revision": d["revision"], "payload": d["data"]["payload"]},
            )["conflict_token"]
            for d in drafts
        }
        result = write(
            c,
            h,
            f"/agent/runs/{run['id']}/resume",
            {
                "approval_id": approval["id"],
                "revision": approval["revision"],
                "decision": "approve",
                "conflict_tokens": tokens,
                "conflict_acknowledged": [d["id"] for d in drafts],
            },
        )
        assert result.status_code == 409
        assert c.get("/api/fixed-events").json() == []
        assert c.get("/api/tasks").json() == before_tasks
        assert all(
            c.get(f"/api/drafts/{d['id']}").json()["data"]["status"] == "pending"
            for d in drafts
        )
        post(
            c,
            h,
            f"/agent/runs/{run['id']}/resume",
            {
                "approval_id": approval["id"],
                "revision": approval["revision"],
                "decision": "reject",
            },
        )
        assert wait_run(c, run["id"])["data"]["status"] == "done"


def test_complete_expansion_with_unknown_campus_requires_explicit_ack(tmp_path):
    from tests.test_conflicts import setup, timetable

    with make_client(tmp_path) as c:
        h = register_login(c)
        setup(c, h)
        d = timetable(c, h, campus=None)
        report = post(
            c,
            h,
            f"/drafts/{d['id']}/conflict-preview",
            {"revision": d["revision"], "payload": d["data"]["payload"]},
        )
        assert (
            report["complete"] is True
            and report["conflict_count"] == 0
            and report["pending_count"] > 0
        )
        c.app.state.agent_model_factory = lambda: ToolModel()
        t = post(c, h, "/agent/threads", {})
        run = wait_run(
            c,
            post(
                c,
                h,
                "/agent/runs",
                {"thread_id": t["id"], "message": "commit:" + d["id"]},
            )["id"],
        )
        a = c.get("/api/agent/approvals/" + run["data"]["approval_id"]).json()
        before = c.get("/api/courses").json()
        body = {
            "approval_id": a["id"],
            "revision": a["revision"],
            "decision": "approve",
            "conflict_tokens": {d["id"]: report["conflict_token"]},
        }
        assert write(c, h, f"/agent/runs/{run['id']}/resume", body).status_code == 409
        assert c.get("/api/courses").json() == before
        accepted = post(
            c,
            h,
            f"/agent/runs/{run['id']}/resume",
            {**body, "conflict_acknowledged": [d["id"]]},
        )
        assert wait_run(c, accepted["id"])["data"]["status"] == "done"
