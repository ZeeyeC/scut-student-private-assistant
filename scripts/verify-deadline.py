"""Billable configured-model deadline probe; only synthetic isolated student data."""

import json
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Config
from app.main import create_app
from tests.test_foundation import register_login


def main():
    cfg = Config()
    if not cfg.model_api_key or not cfg.text_model:
        raise SystemExit("external_input_required: configure a text model")
    with tempfile.TemporaryDirectory(
        prefix="campus-deadline-model-probe-"
    ) as directory:
        root = Path(directory)
        cfg.app_mode = "shared"
        cfg.database_url = f"sqlite+aiosqlite:///{root}/campus.db"
        cfg.agent_db_path = str(root / "agent.db")
        cfg.upload_dir = str(root / "uploads")
        cfg.settings_file = str(root / "model.env")
        cfg.public_origin = "http://testserver"
        cfg.secure_cookie = False
        cfg.registration_enabled = True
        with TestClient(create_app(cfg)) as c:
            headers = register_login(c)

            def post(url, body):
                result = c.post(
                    url, json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
                )
                assert result.status_code == 200, f"{url}: {result.status_code}"
                return result.json()

            def wait(rid):
                end = time.monotonic() + 130
                while time.monotonic() < end:
                    result = c.get(f"/api/agent/runs/{rid}").json()
                    if result["data"]["status"] in {
                        "done",
                        "failed",
                        "waiting_approval",
                    }:
                        return result
                    time.sleep(0.2)
                raise AssertionError("Model probe timed out")

            draft = post(
                "/api/drafts/assignment", {"items": [{"title": "截止探针报告"}]}
            )
            task_id = post(
                f"/api/drafts/{draft['id']}/confirm", {"revision": draft["revision"]}
            )["saved_ids"][0]
            original = c.get(f"/api/tasks/{task_id}").json()
            thread = post("/api/agent/threads", {})
            expected_date = (
                datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=1)
            ).date()
            run = post(
                "/api/agent/runs",
                {
                    "thread_id": thread["id"],
                    "message": "请把截止探针报告的截止时间改为明天晚上8点。",
                },
            )
            run = wait(run["id"])
            assert run["data"]["status"] == "waiting_approval", run["data"].get(
                "error", run["data"]["status"]
            )
            assert c.get(f"/api/tasks/{task_id}").json() == original
            events = [
                json.loads(line[6:])
                for line in c.get(
                    f"/api/agent/runs/{run['id']}/events"
                ).text.splitlines()
                if line.startswith("data: ")
            ]
            names = [
                e["payload"]["name"] for e in events if e["type"] == "tool_started"
            ]
            assert {"get_current_time", "list_tasks", "set_task_deadline"} <= set(
                names
            ), names
            approval = c.get(
                "/api/agent/approvals/" + run["data"]["approval_id"]
            ).json()
            action = next(
                a
                for a in approval["data"]["actions"]
                if a["name"] == "set_task_deadline"
            )
            args = action["args"]
            assert (
                args["task_id"] == task_id and args["revision"] == original["revision"]
            )
            assert args["deadline_type"] == "due_at"
            target = datetime.fromisoformat(args["due_at"]).astimezone(
                ZoneInfo("Asia/Shanghai")
            )
            assert target.date() == expected_date and (target.hour, target.minute) == (
                20,
                0,
            )
            post(
                f"/api/agent/runs/{run['id']}/resume",
                {
                    "approval_id": approval["id"],
                    "revision": approval["revision"],
                    "decision": "approve",
                },
            )
            assert wait(run["id"])["data"]["status"] == "done"
            tasks = c.get("/api/tasks").json()
            assert len(tasks) == 1 and tasks[0]["id"] == task_id
            assert datetime.fromisoformat(tasks[0]["data"]["due_at"]) == target
            assert tasks[0]["revision"] == original["revision"] + 1
            assert c.get("/api/drafts").json() == []
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "source": "configured real model + Deep Agents + official Time MCP",
                        "model": cfg.text_model,
                        "tools": names,
                        "approved_deadline": target.isoformat(),
                        "same_task_updated": True,
                        "saved_tasks": len(tasks),
                        "data": "synthetic isolated database only",
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
