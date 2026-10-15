"""Delayed test-only model exercises actual Deep Agents, DB events and replay."""

import asyncio
import json
import threading
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app import store
from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login


class DelayedStreamModel(ToolModel):
    release: Any

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=[{"type": "reasoning", "reasoning": "private-reasoning"}],
                id="test-output",
            )
        )
        yield ChatGenerationChunk(
            message=AIMessageChunk(content="正在", id="test-output")
        )
        while not self.release.is_set():
            await asyncio.sleep(0.02)
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="完成", id="test-output", chunk_position="last"
            )
        )


def events(c, rid, after=0):
    text = c.get(f"/api/agent/runs/{rid}/events?after={after}").text
    return [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]


def test_tokens_are_persisted_before_model_finishes_and_replay_is_exact(tmp_path):
    gate = threading.Event()
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: DelayedStreamModel(release=gate)
        t = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "t"}
        ).json()
        r = c.post(
            "/api/agent/runs",
            json={"thread_id": t["id"], "message": "流式测试"},
            headers={**h, "Idempotency-Key": "r"},
        ).json()

        owner = c.get("/api/me").json()["id"]

        # Avoid doing a synchronous HTTP request inside the application's loop.
        async def has_delta():
            for _ in range(150):
                async with c.app.state.sessions() as db:
                    rows = await store.rows(db, owner, "agent_event")
                    if any(e.data["type"] == "message_delta" for e in rows):
                        return True
                await asyncio.sleep(0.02)
            return False

        try:
            assert c.portal.call(has_delta), (
                "No text delta was persisted while the model was still generating"
            )
            assert (
                c.get(f"/api/agent/runs/{r['id']}").json()["data"]["status"]
                == "running"
            )
        finally:
            gate.set()
        assert wait_run(c, r["id"])["data"]["status"] == "done"
        all_events = events(c, r["id"])
        deltas = [e for e in all_events if e["type"] == "message_delta"]
        assert "".join(e["payload"]["delta"] for e in deltas) == "正在完成"
        final = next(
            e
            for e in all_events
            if e["type"] == "message" and e["payload"]["role"] == "assistant"
        )
        assert final["payload"]["content"] == "正在完成"
        assert {e["payload"]["message_id"] for e in deltas} == {
            final["payload"]["message_id"]
        }
        assert "private-reasoning" not in json.dumps(all_events)
        cursor = deltas[0]["seq"]
        assert events(c, r["id"], cursor) == [
            e for e in all_events if e["seq"] > cursor
        ]
        cookies = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        assert events(c, r["id"]) == all_events


class NaturalTaskModel(ToolModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(content="已生成待校对草稿，确认后保存。")
                    )
                ]
            )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "create_assignment_draft",
                                "args": {
                                    "title": "阅读文献",
                                    "requirements": [],
                                    "due_text": "明天",
                                    "due_at": None,
                                },
                                "id": "natural-task",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class ChatFlowModel(NaturalTaskModel):
    """Test-only slow stream; all persisted drafts use real domain services."""

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if str(messages[-1].content) == "流式测试":
            yield ChatGenerationChunk(message=AIMessageChunk(content="第一段"))
            await asyncio.sleep(4)
            yield ChatGenerationChunk(message=AIMessageChunk(content="第二段"))
        else:
            result = self._generate(messages, stop, run_manager, **kwargs)
            message = result.generations[0].message
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=message.content, tool_calls=message.tool_calls
                )
            )


def test_natural_task_creates_reviewable_draft_then_idempotent_save(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: NaturalTaskModel()
        t = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "t"}
        ).json()
        body = {"thread_id": t["id"], "message": "帮我增加一个任务：明天阅读文献"}
        headers = {**h, "Idempotency-Key": "r"}
        r = c.post("/api/agent/runs", json=body, headers=headers).json()
        assert wait_run(c, r["id"])["data"]["status"] == "done"
        assert (
            c.post("/api/agent/runs", json=body, headers=headers).json()["id"]
            == r["id"]
        )
        assert c.get("/api/tasks").json() == []
        drafts = c.get("/api/drafts").json()
        assert len(drafts) == 1
        draft = drafts[0]
        item = draft["data"]["payload"]["items"][0]
        assert item["title"] == "阅读文献"
        assert item["due_at"] is None and item["due_text"] == "明天"
        assert "due_at" in item["uncertain_fields"]
        assert any(e["type"] == "draft_ready" for e in events(c, r["id"]))
        url = f"/api/drafts/{draft['id']}/confirm"
        for key in ["save", "save-again"]:
            assert (
                c.post(
                    url,
                    json={"revision": draft["revision"]},
                    headers={**h, "Idempotency-Key": key},
                ).status_code
                == 200
            )
        assert len(c.get("/api/tasks").json()) == 1
