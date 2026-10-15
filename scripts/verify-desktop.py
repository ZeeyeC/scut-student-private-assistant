"""Exercise a real native bundle with isolated data and no Python/Node on PATH.

No school account and no model API call. Synthetic test data only.
"""

import argparse
import asyncio
import http.client
import http.cookiejar
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from langchain_mcp_adapters.client import MultiServerMCPClient

parser = argparse.ArgumentParser()
parser.add_argument("executable", type=Path)
args = parser.parse_args()
executable = args.executable.resolve()
origin = "http://127.0.0.1:5173"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
)
csrf = ""


def request(path, body=None, method=None, extra=None):
    headers = {}
    if body is not None:
        headers = {
            "Content-Type": "application/json",
            "Origin": origin,
            "X-CSRF-Token": csrf,
            "Idempotency-Key": str(uuid4()),
        }
    headers.update(extra or {})
    req = urllib.request.Request(
        origin + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    with opener.open(req, timeout=5) as response:
        raw = response.read()
        return (
            json.loads(raw)
            if raw and "json" in response.headers.get("Content-Type", "")
            else raw
        )


def stopped():
    try:
        request("/api/healthz")
        return False
    except (urllib.error.URLError, ConnectionError, http.client.RemoteDisconnected):
        return True


def wait_stopped():
    for _ in range(80):
        if stopped():
            return
        time.sleep(0.1)
    raise AssertionError("Bundle did not stop")


if not stopped():
    raise SystemExit(
        "Port 5173 must be free; this verifier never stops someone else's service"
    )
with tempfile.TemporaryDirectory(prefix="campus-bundle-verification-") as temporary:
    root = Path(temporary)
    runtime_env = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TMP",
            "TEMP",
            "TMPDIR",
            "HOME",
            "USERPROFILE",
            "LOCALAPPDATA",
        }
    }
    runtime_env["PATH"] = (
        os.path.join(os.environ.get("SYSTEMROOT", "C:/Windows"), "System32")
        if os.name == "nt"
        else "/usr/bin:/bin"
    )

    async def verify_bundled_clock():
        before = datetime.now(ZoneInfo("Asia/Shanghai"))
        client = MultiServerMCPClient(
            {
                "time": {
                    "command": str(executable),
                    "args": ["--time-mcp"],
                    "transport": "stdio",
                    "env": runtime_env,
                }
            },
            handle_tool_errors=False,
        )
        async with asyncio.timeout(15):
            tools = await client.get_tools()
            clock = next(t for t in tools if t.name == "get_current_time")
            blocks = await clock.ainvoke({"timezone": "Asia/Shanghai"})
        value = json.loads(next(b["text"] for b in blocks if b["type"] == "text"))
        after = datetime.now(ZoneInfo("Asia/Shanghai"))
        assert (
            before - timedelta(seconds=1)
            <= datetime.fromisoformat(value["datetime"])
            <= after
        )
        print(
            "PASS: bundled official Time MCP over stdio without installed Python/Node"
        )

    asyncio.run(verify_bundled_clock())
    command = [str(executable), "--data-dir", str(root), "--no-browser"]
    running = False
    try:
        first = subprocess.run(
            command, check=False, cwd=root, env=runtime_env, timeout=130
        )
        assert first.returncode == 0, (
            (root / "desktop-error.txt").read_text()
            if (root / "desktop-error.txt").exists()
            else "Launcher failed"
        )
        running = True
        health = request("/api/healthz")
        assert health["application"] == "campus-companion" and health["mode"] == "local"
        assert not health["model_configured"], (
            "A user's API key was embedded in the bundle"
        )
        assert b'<div id="root">' in request("/")
        csrf = request("/api/csrf")["csrf_token"]
        request("/api/local/session", {})
        owner = request("/api/me")["id"]
        settings = request("/api/settings")
        settings["data"]["daily_limit_minutes"] = 123
        settings["data"]["week1_monday"] = "2026-08-31"
        request("/api/settings", settings, method="PUT")
        academic = [
            request(
                "/api/drafts/assignment",
                {
                    "items": [
                        {"title": f"Native week {week}", "due_text": f"第{week}周之前"}
                    ]
                },
            )
            for week in (14, 11)
        ]
        for d, expected in zip(
            academic, ("2026-11-30T00:00:00+08:00", "2026-11-09T00:00:00+08:00")
        ):
            assert d["data"]["payload"]["items"][0]["due_at"] == expected
            rid = request(
                f"/api/drafts/{d['id']}/confirm", {"revision": d["revision"]}
            )["saved_ids"][0]
            request(f"/api/tasks/{rid}", {"revision": 1}, method="DELETE")
        calendar_boundary = request(
            "/api/drafts/assignment",
            {
                "items": [
                    {"title": "Native calendar boundary", "due_text": "11月1日之前"}
                ]
            },
        )
        year = datetime.now(ZoneInfo("Asia/Shanghai")).year
        assert (
            calendar_boundary["data"]["payload"]["items"][0]["due_at"]
            == f"{year}-11-01T00:00:00+08:00"
        )
        rid = request(
            f"/api/drafts/{calendar_boundary['id']}/confirm",
            {"revision": calendar_boundary["revision"]},
        )["saved_ids"][0]
        request(f"/api/tasks/{rid}", {"revision": 1}, method="DELETE")
        draft = request(
            "/api/drafts/assignment",
            {"items": [{"title": "Native delete verification"}]},
        )
        task_id = request(
            f"/api/drafts/{draft['id']}/confirm", {"revision": draft["revision"]}
        )["saved_ids"][0]
        task = request(f"/api/tasks/{task_id}")
        tool_names = request("/api/agent/tools")["tools"]
        assert len(tool_names) == 18 and {
            "set_task_deadline",
            "set_assignment_draft_deadline",
            "resolve_academic_deadline",
        } <= set(tool_names)
        deadline = (
            (datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=1))
            .replace(hour=20, minute=0, second=0, microsecond=0)
            .isoformat()
        )
        task = request(
            f"/api/tasks/{task_id}",
            {"revision": task["revision"], "due_at": deadline},
            method="PATCH",
        )
        assert task["data"]["due_at"] == deadline
        assert "due_at" not in task["data"]["uncertain_fields"]
        discarded = request(
            "/api/drafts/assignment", {"items": [{"title": "Native discarded draft"}]}
        )
        deletions = []
        for path, revision in [
            (f"/api/tasks/{task_id}", task["revision"]),
            (f"/api/drafts/{discarded['id']}", discarded["revision"]),
        ]:
            headers = {"Idempotency-Key": str(uuid4())}
            result = request(
                path, {"revision": revision}, method="DELETE", extra=headers
            )
            assert result["deleted"]
            deletions.append((path, revision, headers, result))
        assert request("/api/tasks") == [] and request("/api/drafts") == []
        assert request("/api/local/extension-installation")["available"]
        manifest = json.loads(
            (root / "desktop-extension/manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["permissions"] == ["storage", "alarms"]
        assert set(manifest["host_permissions"]) == {
            origin + "/*",
            "http://xsjw2018.jw.scut.edu.cn/*",
        }
        original_pid = (root / "data/campus.db.server.lock").read_text()
        assert (
            subprocess.run(
                command, check=False, cwd=root, env=runtime_env, timeout=15
            ).returncode
            == 0
        )
        assert (root / "data/campus.db.server.lock").read_text() == original_pid, (
            "Double launch spawned another server"
        )
        try:
            request(
                "/api/local/status", extra={"Origin": "https://not-this-app.example"}
            )
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("Cross-origin request was accepted")
        request("/api/local/shutdown", {})
        wait_stopped()
        running = False
        assert (
            subprocess.run(
                command, check=False, cwd=root, env=runtime_env, timeout=130
            ).returncode
            == 0
        )
        running = True
        csrf = request("/api/csrf")["csrf_token"]
        request("/api/local/session", {})
        assert request("/api/me")["id"] == owner
        assert request("/api/settings")["data"]["daily_limit_minutes"] == 123
        for path, revision, headers, result in deletions:
            assert (
                request(path, {"revision": revision}, method="DELETE", extra=headers)
                == result
            )
        assert request("/api/tasks") == [] and request("/api/drafts") == []
        request("/api/local/shutdown", {})
        wait_stopped()
        running = False
        print(
            "PASS: real native bundle, static GUI, bundled extension, no model key, local session, persistence, deadline update service/tool list, task/draft deletion and replay after restart, duplicate launch, cross-origin rejection, restart and graceful stop. No Python/Node on runtime PATH."
        )
    finally:
        if running and not stopped():
            try:
                request("/api/local/shutdown", {})
                wait_stopped()
            except Exception:
                print(
                    "Verification service requires manual shutdown; isolated directory:",
                    root,
                )
                raise
