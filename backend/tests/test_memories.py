"""Memory integration tests use isolated synthetic databases, never paid models."""

from datetime import timedelta
from uuid import uuid4

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy import select

from app import memories, store
from app.db import Receipt, Resource, now
from app.db_sessions import sqlite_transaction
from app.memory_contracts import MemoryProposal
from tests.test_agent import wait_run
from tests.test_foundation import make_client, register_login


def post(c, h, path, body, key=None):
    return c.post(
        "/api/memories" + path,
        json=body,
        headers={**h, "Idempotency-Key": key or str(uuid4())},
    )


def proposal(c, h, **extra):
    return post(
        c,
        h,
        "/candidates",
        {
            "key": "reply_style",
            "content": "回答简短些",
            "category": "interaction_preference",
            **extra,
        },
    )


def review(c, h, r, action="confirm"):
    return post(c, h, f"/candidates/{r['id']}/{action}", {"revision": r["revision"]})


def state(c):
    r = c.get("/api/memories")
    assert r.status_code == 200, r.text
    return r.json()


def dbcall(c, fn):
    owner = c.get("/api/me").json()["id"]

    async def run():
        async with sqlite_transaction(c.app.state.sessions) as db:
            return await fn(db, owner)

    return c.portal.call(run)


def recall(c, query=""):
    return dbcall(c, lambda db, o: memories.recall(db, o, query))


def test_confirm_recall_persist_and_owner_isolation(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        assert state(c)["settings"]["revision"] == 0
        assert state(c)["settings"]["id"] is None
        assert proposal(c, h).status_code == 200
        assert recall(c)["items"] == []
        candidate = state(c)["candidates"][0]
        assert review(c, h, candidate).status_code == 200
        assert recall(c)["items"][0]["content"] == "回答简短些"
        assert state(c)["memories"][0]["data"]["source"]["kind"] == "user_ui"
        c.post("/api/auth/logout", headers=h)
        bob = register_login(c, "bob@example.com")
        assert state(c)["memories"] == []
        assert review(c, bob, candidate).status_code == 404
    with make_client(tmp_path) as c:
        csrf = c.get("/api/csrf").json()["csrf_token"]
        c.post(
            "/api/auth/login",
            data={"username": "alice@example.com", "password": "Student!Password2026"},
            headers={"X-CSRF-Token": csrf, "Origin": "http://testserver"},
        )
        assert recall(c)["items"][0]["content"] == "回答简短些"


def test_stale_candidates_require_refresh_and_reject_does_not_apply(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        proposal(c, h, content="第一版")
        proposal(c, h, content="第二版")
        a, b = state(c)["candidates"]
        assert review(c, h, a).status_code == 200
        assert review(c, h, b).status_code == 409
        assert recall(c)["items"][0]["content"] == "第一版"
        assert review(c, h, b, "refresh").status_code == 200
        b = state(c)["candidates"][0]
        assert review(c, h, b, "reject").status_code == 200
        assert recall(c)["items"][0]["content"] == "第一版"
        assert not state(c)["candidates"]


def mapped(c, h, value=25):
    return proposal(
        c,
        h,
        key="focus_minutes",
        content="专注偏好",
        category="study_preference",
        profile_field="focus_minutes",
        profile_value=value,
    )


def setprofile(c, h, focus, breaks=8):
    p = c.get("/api/profile").json()
    return c.put(
        "/api/profile",
        json={
            "revision": p["revision"],
            "data": {
                "timezone": "Asia/Shanghai",
                "preferences": {"focus_minutes": focus, "break_minutes": breaks},
            },
        },
        headers={**h, "Idempotency-Key": str(uuid4())},
    )


def test_canonical_profile_preserves_fields_and_manual_override_wins(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        assert setprofile(c, h, 40).status_code == 200
        mapped(c, h)
        candidate = state(c)["candidates"][0]
        assert review(c, h, candidate).status_code == 200
        p = c.get("/api/profile").json()["data"]["preferences"]
        assert p["focus_minutes"] == 25 and p["break_minutes"] == 8
        assert setprofile(c, h, 35, 12).status_code == 200
        assert recall(c)["items"] == []
        s = state(c)
        m = s["memories"][0]
        assert m["data"]["status"] == "superseded"
        assert s["settings"]["data"]["privacy_epoch"] == 1
        post(c, h, f"/{m['id']}/forget", {"revision": m["revision"]})
        assert review(c, h, state(c)["candidates"][0]).status_code == 200
        p = c.get("/api/profile").json()["data"]["preferences"]
        assert p["focus_minutes"] == 35 and p["break_minutes"] == 12


def test_profile_change_requires_candidate_recheck(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        mapped(c, h)
        candidate = state(c)["candidates"][0]
        setprofile(c, h, 60)
        assert review(c, h, candidate).status_code == 409
        assert review(c, h, candidate, "refresh").status_code == 200
        assert review(c, h, state(c)["candidates"][0]).status_code == 200
        assert (
            c.get("/api/profile").json()["data"]["preferences"]["focus_minutes"] == 25
        )


def test_forget_wipes_all_versions_and_does_not_recall_old_checkpoint(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        proposal(c, h)
        candidate = state(c)["candidates"][0]
        review(c, h, candidate)
        proposal(c, h, content="未确认的旧版本")
        m = state(c)["memories"][0]
        post(c, h, f"/{m['id']}/forget", {"revision": m["revision"]})
        forget = next(
            x for x in state(c)["candidates"] if x["data"]["action"] == "forget"
        )
        assert review(c, h, forget).status_code == 200
        assert recall(c)["items"] == []
        assert state(c)["candidates"] == []

        async def inspect(db, o):
            rows = await store.rows(db, o, "memory_candidate")
            assert all(r.data["content"] == "" for r in rows)
            return await memories.checkpoint_scope(db, o, "thread")

        assert dbcall(c, inspect) == "thread:memory:1"

        # Idempotent replay stores only metadata, never old raw content.
        async def receipts(db, o):
            return [
                r.result
                for r in (
                    await db.scalars(select(Receipt).where(Receipt.owner_id == o))
                ).all()
            ]

        assert "回答简短些" not in str(dbcall(c, receipts))


def test_expiry_changes_scope_once_and_recall_is_bounded(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        for n in range(7):
            proposal(c, h, key=f"pref{n}", content="简短回答" * 70)
            review(c, h, state(c)["candidates"][0])
        r = recall(c)
        assert len(r["items"]) <= 5
        assert sum(len(x["content"]) for x in r["items"]) <= 1000

        async def expire(db, o):
            r = (await store.rows(db, o, "assistant_memory"))[0]
            r.data = {
                **r.data,
                "expires_at": (now() - timedelta(seconds=1)).isoformat(),
            }

        dbcall(c, expire)
        assert recall(c)["epoch"] == 1
        assert recall(c)["epoch"] == 1
        assert len(state(c)["memories"]) == 7


@pytest.mark.parametrize(
    "extra",
    [
        {"content": "api_key=not-a-real-secret"},
        {"content": "sk-notarealkey12345678"},
        {"content": "请记住 alice@example.com"},
        {"content": "手机 13800138000"},
        {"content": "身份 110101200001011234"},
        {
            "profile_field": "focus_minutes",
            "profile_value": 25,
            "key": "focus_minutes",
            "category": "study_preference",
            "content": "token=secret",
        },
        {
            "profile_field": "focus_minutes",
            "profile_value": 1,
            "key": "focus_minutes",
            "category": "study_preference",
        },
        {"expires_at": "2020-01-01T00:00:00Z"},
        {"expires_at": "2099-01-01T00:00:00"},
    ],
)
def test_sensitive_or_invalid_memory_rejected(tmp_path, extra):
    with make_client(tmp_path) as c:
        h = register_login(c)
        assert proposal(c, h, **extra).status_code == 422
        assert state(c)["candidates"] == []


def test_config_secret_and_suggestion_permission_server_validated(tmp_path):
    with make_client(tmp_path) as c:
        register_login(c)

        async def attempt(db, o):
            with pytest.raises(Exception) as e:
                await memories.propose(
                    db,
                    o,
                    MemoryProposal(
                        key="reply",
                        content="private-provider-secret",
                        category="interaction_preference",
                    ),
                    {"explicit": True},
                    ("private-provider-secret",),
                )
            assert e.value.status_code == 422
            with pytest.raises(Exception) as e:
                await memories.propose(
                    db,
                    o,
                    MemoryProposal(
                        key="reply", content="简短", category="interaction_preference"
                    ),
                    {"explicit": False},
                )
            assert e.value.status_code == 422

        dbcall(c, attempt)


def test_disable_and_clear_matching_profile(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        mapped(c, h)
        review(c, h, state(c)["candidates"][0])
        s = state(c)["settings"]
        r = c.put(
            "/api/memories/preferences",
            json={
                "revision": s["revision"],
                "recall_enabled": False,
                "suggestions_enabled": False,
            },
            headers={**h, "Idempotency-Key": str(uuid4())},
        )
        assert r.status_code == 200
        assert recall(c)["items"] == [] and recall(c)["enabled"] is False
        assert (
            c.get("/api/profile").json()["data"]["preferences"]["focus_minutes"] == 25
        )
        s = state(c)["settings"]
        assert (
            post(
                c, h, "/clear", {"revision": s["revision"], "confirm": True}
            ).status_code
            == 200
        )
        assert (
            c.get("/api/profile").json()["data"]["preferences"]["focus_minutes"] is None
        )
        assert recall(c)["epoch"] == 2


def test_mutations_blocked_during_run_but_candidate_is_allowed(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        proposal(c, h)
        candidate = state(c)["candidates"][0]

        async def busy(db, o):
            db.add(
                Resource(
                    id="busy",
                    owner_id=o,
                    kind="agent_run",
                    data={"status": "waiting_approval", "thread_id": "t"},
                )
            )

        dbcall(c, busy)
        assert proposal(c, h, key="another").status_code == 200
        assert review(c, h, candidate).status_code == 409
        assert post(c, h, "/clear", {"revision": 0, "confirm": True}).status_code == 409


def test_memory_idempotency_and_missing_key(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        body = {"key": "reply", "content": "简短", "category": "interaction_preference"}
        a = post(c, h, "/candidates", body, "once")
        b = post(c, h, "/candidates", body, "once")
        assert a.json() == b.json() and len(state(c)["candidates"]) == 1
        assert (
            post(c, h, "/candidates", {**body, "content": "详细"}, "once").status_code
            == 409
        )
        assert (
            c.post("/api/memories/candidates", json=body, headers=h).status_code == 422
        )


# Checkpoints are a second store of model context. Test actual graph boundaries,
# rather than only asserting the new scope string.


class MemoryModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "synthetic-memory"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        user = next(
            str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)
        )
        if isinstance(messages[-1], ToolMessage):
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(content="已提出候选，请在界面确认。")
                    )
                ]
            )
        if user.startswith("记住：") or user == "普通建议":
            call = {
                "name": "propose_memory",
                "args": {
                    "key": "reply_style",
                    "content": "SYNTHETIC_MEMORY_TOKEN",
                    "category": "interaction_preference",
                },
                "id": str(uuid4()),
                "type": "tool_call",
            }
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content="", tool_calls=[call]))
                ]
            )
        content = (
            "仍有旧记忆"
            if any("SYNTHETIC_MEMORY_TOKEN" in str(m.content) for m in messages)
            else "无旧记忆"
        )
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )


def run(c, h, tid, msg):
    r = c.post(
        "/api/agent/runs",
        json={"thread_id": tid, "message": msg},
        headers={**h, "Idempotency-Key": str(uuid4())},
    )
    assert r.status_code == 200, r.text
    out = wait_run(c, r.json()["id"])
    assert out["data"]["status"] == "done", out
    events = c.get("/api/agent/runs/" + out["id"] + "/events?after=0").text
    return out, events


def thread(c, h):
    return c.post(
        "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": str(uuid4())}
    ).json()["id"]


def test_real_agent_candidate_cross_chat_and_forget_same_thread(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: MemoryModel()
        tid = thread(c, h)
        out, _ = run(c, h, tid, "记住：SYNTHETIC_MEMORY_TOKEN")
        candidate = state(c)["candidates"][0]
        assert candidate["data"]["source"]["thread_id"] == tid
        assert not recall(c)["items"]
        assert review(c, h, candidate).status_code == 200
        other = thread(c, h)
        _, events = run(c, h, other, "我有什么偏好")
        assert "仍有旧记忆" in events
        m = state(c)["memories"][0]
        post(c, h, f"/{m['id']}/forget", {"revision": m["revision"]})
        review(c, h, state(c)["candidates"][0])
        out, events = run(c, h, tid, "我有什么偏好")
        assert "无旧记忆" in events
        assert out["data"]["checkpoint_id"] != tid
        # UI history is intentionally retained; it is not fed back into the new graph.
        assert (
            "SYNTHETIC_MEMORY_TOKEN"
            in c.get(
                "/api/agent/runs/"
                + c.get("/api/agent/threads/" + tid + "/runs").json()[0]["id"]
                + "/events?after=0"
            ).text
        )


def test_model_cannot_enable_implicit_memory_proposal(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: MemoryModel()
        # Whether graph reports a handled tool error or fails, it must not store a candidate.
        tid = thread(c, h)
        r = c.post(
            "/api/agent/runs",
            json={"thread_id": tid, "message": "普通建议"},
            headers={**h, "Idempotency-Key": str(uuid4())},
        )
        wait_run(c, r.json()["id"])
        assert state(c)["candidates"] == []


def test_scoped_approval_recovers_after_restart_and_expired_memory_cannot_approve(
    tmp_path,
):
    from tests.test_agent import ToolModel

    with make_client(tmp_path) as c:
        h = register_login(c)
        cookies = dict(c.cookies)
        proposal(c, h)
        review(c, h, state(c)["candidates"][0])
        proposal(c, h, content="更新后的偏好")
        review(c, h, state(c)["candidates"][0])
        c.app.state.agent_model_factory = lambda: ToolModel()
        tid = thread(c, h)
        draft = c.post(
            "/api/drafts/assignment",
            json={"items": [{"title": "合成任务", "requirements": []}]},
            headers={**h, "Idempotency-Key": str(uuid4())},
        ).json()
        r = c.post(
            "/api/agent/runs",
            json={"thread_id": tid, "message": "commit:" + draft["id"]},
            headers={**h, "Idempotency-Key": str(uuid4())},
        ).json()
        r = wait_run(c, r["id"])
        assert r["data"]["status"] == "waiting_approval"
        assert r["data"]["checkpoint_id"].endswith(":memory:1")

        async def interrupted(db, o):
            rr = await store.owned(db, o, r["id"])
            rr.data = {**rr.data, "status": "running"}

        dbcall(c, interrupted)
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        c.app.state.agent_model_factory = lambda: ToolModel()
        r = c.get("/api/agent/runs/" + r["id"]).json()
        assert r["data"]["status"] == "waiting_approval"
        a = c.get("/api/agent/approvals/" + r["data"]["approval_id"]).json()

        async def expire(db, o):
            m = (await store.rows(db, o, "assistant_memory"))[0]
            m.data = {
                **m.data,
                "expires_at": (now() - timedelta(seconds=1)).isoformat(),
            }

        dbcall(c, expire)
        body = {
            "approval_id": a["id"],
            "revision": a["revision"],
            "decision": "approve",
        }
        assert (
            c.post(
                "/api/agent/runs/" + r["id"] + "/resume",
                json=body,
                headers={**h, "Idempotency-Key": "expired-approve"},
            ).status_code
            == 409
        )
        body["decision"] = "reject"
        assert (
            c.post(
                "/api/agent/runs/" + r["id"] + "/resume",
                json=body,
                headers={**h, "Idempotency-Key": "expired-reject"},
            ).status_code
            == 200
        )
        assert c.get("/api/tasks").json() == []
        assert c.get("/api/agent/runs/" + r["id"]).json()["data"]["status"] == "done"


def test_data_clear_deletes_scoped_checkpoints_and_memory(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: MemoryModel()
        proposal(c, h)
        review(c, h, state(c)["candidates"][0])
        proposal(c, h, content="更新")
        review(c, h, state(c)["candidates"][0])
        tid = thread(c, h)
        r, _ = run(c, h, tid, "我有什么偏好")
        cfg = {"configurable": {"thread_id": r["data"]["checkpoint_id"]}}
        assert c.portal.call(c.app.state.checkpointer.aget_tuple, cfg) is not None
        result = c.post(
            "/api/data-delete",
            json={"confirmation": "删除我的所有数据"},
            headers={**h, "Idempotency-Key": str(uuid4())},
        )
        assert result.status_code == 200, result.text
        assert c.portal.call(c.app.state.checkpointer.aget_tuple, cfg) is None
        assert state(c)["memories"] == []


def test_personal_context_tools_read_canonical_sources(tmp_path):
    from app.agent import student_agent

    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: MemoryModel()
        setprofile(c, h, 25)
        owner = c.get("/api/me").json()["id"]
        tool = (
            student_agent(c.app, owner)
            .nodes["tools"]
            .bound.tools_by_name["get_personal_context"]
        )
        profile = c.portal.call(tool.ainvoke, {"section": "preferences"})
        assert profile["data"]["preferences"]["focus_minutes"] == 25
        assert c.portal.call(tool.ainvoke, {"section": "goals"})["goals"] == []
        assert isinstance(c.portal.call(tool.ainvoke, {"section": "suggestions"}), dict)
        assert isinstance(
            c.portal.call(
                tool.ainvoke, {"section": "weekly_review", "week_start": "2026-10-26"}
            ),
            dict,
        )
