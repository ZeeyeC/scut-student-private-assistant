"""Read-only literature connector boundaries; synthetic local configuration."""

from pathlib import Path
from uuid import uuid4
import pytest
from fastapi import HTTPException


def test_readonly_whitelist_and_remote_url_rules():
    from app.zotero_bridge import ALLOWED, validate_endpoint

    assert ALLOWED == {
        "zotero_search_items",
        "zotero_get_item_metadata",
        "zotero_get_item_fulltext",
        "zotero_get_annotations",
        "zotero_get_notes",
        "zotero_get_collections",
    }
    assert validate_endpoint("https://example.com/mcp") == "https://example.com/mcp"
    for url in [
        "file:///tmp/x",
        "http://example.com/mcp",
        "https://u:p@example.com/mcp",
        "https://example.com/mcp?key=x",
        "https://example.com/\\x",
    ]:
        with pytest.raises(HTTPException):
            validate_endpoint(url)


@pytest.mark.anyio
async def test_upstream_worker_has_only_read_tools_and_no_background_lifespan(
    tmp_path, monkeypatch
):
    import os

    for name in [
        "HOME",
        "PYTHON_DOTENV_DISABLED",
        "ZOTERO_LOCAL",
        "ZOTERO_BACKEND",
        "ZOTERO_MCP_TOOLSETS",
        "ZOTERO_NO_CLAUDE",
        "ZOTERO_MCP_LOCK_TIMEOUT",
        "ZOTERO_API_KEY",
        "ZOTERO_LOCAL_API_KEY",
        "ZOTERO_LIBRARY_ID",
    ]:
        monkeypatch.setenv(name, os.environ.get(name, ""))
    from app.zotero_worker import safe_server

    server = await safe_server(tmp_path)
    tools = await server.list_tools()
    from app.zotero_bridge import ALLOWED

    assert {t.name for t in tools} == ALLOWED


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_settings_secret_is_private_and_read_calls_are_review_only(tmp_path):
    from tests.test_local_mode import local_client, headers
    from app.zotero_bridge import read_token

    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)

        def put(body):
            return c.put(
                "/api/zotero/settings",
                json=body,
                headers={**h, "Idempotency-Key": str(uuid4())},
            )

        start = c.get("/api/zotero/status")
        assert start.status_code == 200, start.text
        assert start.json()["enabled"] is False and start.json()["connected"] is None
        body = {
            "revision": 0,
            "enabled": True,
            "mode": "remote",
            "endpoint": "https://example.com/mcp",
            "token": "synthetic-zotero-private-token",
        }
        saved = put(body)
        assert saved.status_code == 200, saved.text
        assert "synthetic-zotero-private-token" not in saved.text
        owner = c.get("/api/me").json()["id"]
        assert read_token(c.app.state.config, owner) == body["token"]
        assert put(body).status_code == 409
        calls = []

        async def fake(config, data, token, name, args, test=False):
            calls.append((name, args))
            assert token == body["token"]
            return {
                "text": "Synthetic calculus paper · ABCD1234",
                "tools": ["zotero_search_items"],
                "untrusted": True,
                "read_only": True,
            }

        c.app.state.zotero_invoker = fake
        r = c.post("/api/zotero/search", json={"query": "微积分"}, headers=h)
        assert r.status_code == 200, r.text
        assert calls[0][0] == "zotero_search_items"
        assert (
            c.get("/api/tasks").json() == []
            and c.get("/api/memories").json()["memories"] == []
        )
        assert body["token"] not in c.get("/api/data-export").text
        c.post(
            "/api/data-delete",
            json={"confirmation": "删除我的所有数据"},
            headers={**h, "Idempotency-Key": "clear"},
        )
        assert read_token(c.app.state.config, owner) == ""


def test_frozen_mcp_child_restores_standard_pipes(monkeypatch):
    import sys
    from app import launcher

    for name in ("stdin", "stdout", "stderr"):
        monkeypatch.setattr(sys, name, None)
    launcher.restore_pipe_streams()
    assert (
        sys.stdin.buffer is not None
        and sys.stdout.buffer is not None
        and sys.stderr.buffer is not None
    )


def test_clear_and_recreate_connection_cannot_release_old_library_response(tmp_path):
    import threading, asyncio
    from tests.test_local_mode import local_client, headers

    started, release = threading.Event(), threading.Event()
    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)

        def save(url):
            return c.put(
                "/api/zotero/settings",
                json={
                    "revision": 0,
                    "enabled": True,
                    "mode": "remote",
                    "endpoint": url,
                },
                headers={**h, "Idempotency-Key": str(uuid4())},
            )

        assert save("https://old.example/mcp").status_code == 200

        async def paused(*a, **kw):
            started.set()
            await asyncio.to_thread(release.wait, 10)
            return {"text": "OLD LIBRARY CONTENT", "tools": []}

        c.app.state.zotero_invoker = paused
        results = []
        worker = threading.Thread(
            target=lambda: results.append(
                c.post("/api/zotero/search", json={"query": "paper"}, headers=h)
            )
        )
        worker.start()
        assert started.wait(5)
        assert (
            c.post(
                "/api/data-delete",
                json={"confirmation": "删除我的所有数据"},
                headers={**h, "Idempotency-Key": "clear"},
            ).status_code
            == 200
        )
        assert save("https://new.example/mcp").status_code == 200
        release.set()
        worker.join(10)
        assert (
            results[0].status_code == 409
            and "OLD LIBRARY CONTENT" not in results[0].text
        )


def test_secret_from_uncommitted_other_endpoint_is_not_sent(tmp_path):
    from tests.test_local_mode import local_client, headers
    from app.zotero_bridge import secret_path
    import json

    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)
        response = c.put(
            "/api/zotero/settings",
            json={
                "revision": 0,
                "enabled": True,
                "mode": "remote",
                "endpoint": "https://old.example/mcp",
                "token": "old-synthetic",
            },
            headers={**h, "Idempotency-Key": "settings"},
        )
        assert response.status_code == 200
        owner = c.get("/api/me").json()["id"]
        p = secret_path(c.app.state.config, owner)
        p.write_text(
            json.dumps(
                {
                    "zotero_token": "new-private-synthetic",
                    "binding": "different-endpoint-and-revision",
                }
            )
        )
        observed = []

        async def fake(config, data, token, *a, **kw):
            observed.append(token)
            return {"text": "synthetic result", "tools": []}

        c.app.state.zotero_invoker = fake
        response = c.post("/api/zotero/search", json={"query": "paper"}, headers=h)
        assert observed == [""] and response.status_code == 200


def test_notes_and_annotations_do_not_mix_connections(tmp_path):
    from tests.test_local_mode import local_client, headers
    import threading, asyncio

    first, release = threading.Event(), threading.Event()
    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)
        response = c.put(
            "/api/zotero/settings",
            json={
                "revision": 0,
                "enabled": True,
                "mode": "remote",
                "endpoint": "https://old.example/mcp",
            },
            headers={**h, "Idempotency-Key": "old"},
        )
        rev = response.json()["revision"]

        async def fake(config, data, token, name, args, test=False):
            if name == "zotero_get_annotations":
                first.set()
                await asyncio.to_thread(release.wait, 10)
            return {"text": data["endpoint"], "tools": []}

        c.app.state.zotero_invoker = fake
        results = []
        t = threading.Thread(
            target=lambda: results.append(
                c.post(
                    "/api/zotero/item",
                    json={"item_key": "ABCD1234", "section": "notes"},
                    headers=h,
                )
            )
        )
        t.start()
        assert first.wait(5)
        r = c.put(
            "/api/zotero/settings",
            json={
                "revision": rev,
                "enabled": True,
                "mode": "remote",
                "endpoint": "https://new.example/mcp",
            },
            headers={**h, "Idempotency-Key": "new"},
        )
        assert r.status_code == 200
        release.set()
        t.join(10)
        assert results[0].status_code == 409


@pytest.mark.anyio
async def test_invoke_rejects_write_tools_without_transport():
    from app.zotero_bridge import invoke
    from app.config import Config

    with pytest.raises(HTTPException) as e:
        await invoke(
            Config(_env_file=None),
            {"mode": "local"},
            "",
            "zotero_delete_item",
            {"item_key": "ABCD1234"},
        )
    assert e.value.status_code == 403


def test_default_disabled_and_invalid_inputs_do_not_connect(tmp_path):
    from tests.test_local_mode import local_client, headers

    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)

        async def forbidden(*a, **kw):
            raise AssertionError("Disabled connector must not run")

        c.app.state.zotero_invoker = forbidden
        assert (
            c.post("/api/zotero/search", json={"query": "paper"}, headers=h).status_code
            == 409
        )
        assert (
            c.post("/api/zotero/item", json={"item_key": "../x"}, headers=h).status_code
            == 422
        )
        r = c.put(
            "/api/zotero/settings",
            json={
                "revision": 0,
                "enabled": True,
                "mode": "remote",
                "endpoint": "https://example.com/mcp",
                "token": "SECRET\nHEADER",
            },
            headers={**h, "Idempotency-Key": "invalid"},
        )
        assert (
            r.status_code == 422 and "SECRET" not in r.text and "HEADER" not in r.text
        )


def test_failed_retest_clears_previous_connected_status(tmp_path):
    from tests.test_local_mode import local_client, headers

    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)
        c.put(
            "/api/zotero/settings",
            json={"revision": 0, "enabled": True, "mode": "local"},
            headers={**h, "Idempotency-Key": "settings"},
        )

        async def success(*a, **kw):
            return {"text": "[]", "tools": []}

        c.app.state.zotero_invoker = success
        assert c.post("/api/zotero/test", json={}, headers=h).status_code == 200
        assert c.get("/api/zotero/status").json()["connected"] is True

        async def failed(*a, **kw):
            raise HTTPException(422, "连接失败")

        c.app.state.zotero_invoker = failed
        assert c.post("/api/zotero/test", json={}, headers=h).status_code == 422
        assert c.get("/api/zotero/status").json()["connected"] is False


def test_agent_reads_library_tool_without_creating_tasks_or_memories(tmp_path):
    from tests.test_local_mode import local_client, headers
    from tests.test_agent import ToolModel, wait_run
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatResult, ChatGeneration

    class PaperModel(ToolModel):
        def _generate(self, messages, stop=None, run_manager=None, **kw):
            if isinstance(messages[-1], ToolMessage):
                message = AIMessage(
                    content="合成论文 Synthetic calculus paper，条目 ABCD1234。"
                )
            else:
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_zotero_papers",
                            "args": {"query": "calculus"},
                            "id": "paper-read",
                            "type": "tool_call",
                        }
                    ],
                )
            return ChatResult(generations=[ChatGeneration(message=message)])

    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)
        c.put(
            "/api/zotero/settings",
            json={"revision": 0, "enabled": True, "mode": "local"},
            headers={**h, "Idempotency-Key": "settings"},
        )

        async def fake(config, data, token, name, args, test=False):
            assert name == "zotero_search_items" and args["query"] == "calculus"
            return {
                "text": "Synthetic calculus paper ABCD1234",
                "tools": [name],
                "untrusted": True,
            }

        c.app.state.zotero_invoker = fake
        c.app.state.agent_model_factory = lambda: PaperModel()
        tid = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "thread"}
        ).json()["id"]
        response = c.post(
            "/api/agent/runs",
            json={"thread_id": tid, "message": "查询我的Zotero论文"},
            headers={**h, "Idempotency-Key": "run"},
        )
        assert response.status_code == 200, response.text
        run = wait_run(c, response.json()["id"])
        assert run["data"]["status"] == "done", run
        events = c.get("/api/agent/runs/" + run["id"] + "/events?after=0").text
        assert "search_zotero_papers" in events and "ABCD1234" in events
        assert (
            c.get("/api/tasks").json() == []
            and c.get("/api/memories").json()["memories"] == []
        )


@pytest.mark.anyio
async def test_remote_tool_listing_handles_mcp_pagination(monkeypatch):
    from app import zotero_bridge as bridge
    from app.config import Config
    from types import SimpleNamespace as NS
    from contextlib import asynccontextmanager

    cursors = []

    class Session:
        async def list_tools(self, cursor=None):
            cursors.append(cursor)
            return NS(
                tools=[NS(name="other_tool")]
                if cursor is None
                else [NS(name="zotero_search_items")],
                nextCursor="second" if cursor is None else None,
            )

        async def call_tool(self, name, args):
            return NS(isError=False, content=[NS(type="text", text="Synthetic search")])

    class Client:
        def __init__(self, *a, **kw):
            pass

        @asynccontextmanager
        async def session(self, name):
            yield Session()

    monkeypatch.setattr(bridge, "MultiServerMCPClient", Client)
    result = await bridge.invoke(
        Config(_env_file=None),
        {"mode": "remote", "endpoint": "https://example.com/mcp"},
        "",
        "zotero_search_items",
        {"query": "paper"},
    )
    assert result["text"] == "Synthetic search" and cursors == [None, "second"]
