"""Opt-in, billable real-agent probe using synthetic data and separate processes.

Run from the project root. No production account, task, or checkpoint is modified.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Config
from app.main import create_app


def wait_run(client, run_id):
    until = time.monotonic() + 130
    while time.monotonic() < until:
        response = client.get("/api/agent/runs/" + run_id)
        assert response.status_code == 200, "run read failed"
        run = response.json()
        if run["data"]["status"] in {"done", "failed", "waiting_approval"}:
            return run
        time.sleep(0.25)
    raise AssertionError("run timeout")


def worker(phase, directory):
    root = Path(directory)
    cfg = Config()
    cfg.app_mode = "shared"
    cfg.database_url = f"sqlite+aiosqlite:///{root}/campus.db"
    cfg.agent_db_path = str(root / "agent.db")
    cfg.upload_dir = str(root / "uploads")
    cfg.public_origin = "http://testserver"
    cfg.secure_cookie = False
    cfg.registration_enabled = True
    with TestClient(create_app(cfg)) as client:
        if phase == "resume":
            state = json.loads((root / "synthetic-state.json").read_text())
            client.cookies.update(state["cookies"])
        headers = {
            "Origin": "http://testserver",
            "X-CSRF-Token": client.get("/api/csrf").json()["csrf_token"],
        }

        def post(url, payload):
            result = client.post(
                url, json=payload, headers={**headers, "Idempotency-Key": str(uuid4())}
            )
            assert result.status_code in {200, 201}, (
                f"{url} returned {result.status_code}"
            )
            return result.json()

        if phase == "request":
            email = "synthetic-probe@example.com"
            post(
                "/api/auth/register",
                {"email": email, "password": "Synthetic!Probe2026"},
            )
            assert (
                client.post(
                    "/api/auth/login",
                    data={"username": email, "password": "Synthetic!Probe2026"},
                    headers=headers,
                ).status_code
                == 204
            )
            assert len(client.get("/api/agent/tools").json()["tools"]) == 12
            thread = post("/api/agent/threads", {})
            run = post(
                "/api/agent/runs",
                {
                    "thread_id": thread["id"],
                    "message": "请调用 list_tasks 查询我的未完成作业，用中文简短报告结果。这里只查询，不创建或更改任何数据。",
                },
            )
            run = wait_run(client, run["id"])
            assert run["data"]["status"] == "done", "real query failed"
            events = client.get("/api/agent/runs/" + run["id"] + "/events?after=0").text
            assert "list_tasks" in events and "tool_finished" in events, (
                "real business tool not executed"
            )
            print(
                "PASS: real Luna -> Deep Agents -> authenticated list_tasks -> SSE completion",
                flush=True,
            )
            draft = post(
                "/api/drafts/assignment",
                {
                    "items": [
                        {"title": "虚构验收作业", "requirements": ["仅用于接口验收"]}
                    ]
                },
            )
            run = post(
                "/api/agent/runs",
                {
                    "thread_id": thread["id"],
                    "message": f"这是我已校对的测试草稿。请调用 commit_import，draft_id={draft['id']}，revision=1。我会在界面确认面板批准，请先发起待确认操作。不要创建其他草稿或任务。",
                },
            )
            run = wait_run(client, run["id"])
            assert run["data"]["status"] == "waiting_approval", (
                "write did not reach human approval"
            )
            assert client.get("/api/tasks").json() == [], (
                "task written without approval"
            )
            approval = client.get(
                "/api/agent/approvals/" + run["data"]["approval_id"]
            ).json()
            state = {
                "cookies": dict(client.cookies),
                "run_id": run["id"],
                "approval_id": approval["id"],
                "revision": approval["revision"],
            }
            path = root / "synthetic-state.json"
            path.write_text(json.dumps(state))
            path.chmod(0o600)
            print(
                "PASS: real model write request paused; database contains no task before approval",
                flush=True,
            )
        else:
            decision = {k: state[k] for k in ["approval_id", "revision"]}
            decision["decision"] = "approve"
            for _ in range(2):
                post("/api/agent/runs/" + state["run_id"] + "/resume", decision)
            done = wait_run(client, state["run_id"])
            assert done["data"]["status"] == "done", "real model continuation failed"
            tasks = client.get("/api/tasks").json()
            assert len(tasks) == 1 and tasks[0]["data"]["title"] == "虚构验收作业", (
                "approved write was lost or duplicated"
            )
            print(
                "PASS: process restart -> persistent checkpoint -> approval -> real model continuation; duplicate approval saved once",
                flush=True,
            )


def main():
    if len(sys.argv) == 3 and sys.argv[1] in {"request", "resume"}:
        worker(sys.argv[1], sys.argv[2])
        return 0
    cfg = Config()
    if not (cfg.model_api_key and cfg.text_model):
        print("external_input_required: configure MODEL_API_KEY and TEXT_MODEL in .env")
        return 2
    with tempfile.TemporaryDirectory(prefix="campus-real-agent-") as directory:
        for phase in ["request", "resume"]:
            # Each process creates its own async HTTP pool, as a real restart does.
            subprocess.run([sys.executable, __file__, phase, directory], check=True)
    print("PASS: synthetic account/data only; production student data untouched.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print("FAIL:", str(exc))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 -- Do not print provider bodies/credentials.
        print("FAIL:", type(exc).__name__, "provider/app error; details suppressed")
        sys.exit(1)
