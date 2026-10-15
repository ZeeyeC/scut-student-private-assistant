"""Billable real-model probe; isolated data, no student task saved."""

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Config
from app.main import create_app
from tests.test_foundation import register_login


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calendar", action="store_true")
    calendar = parser.parse_args().calendar
    cfg = Config()
    if not cfg.model_api_key or not cfg.text_model:
        raise SystemExit("external_input_required: configure model in the app")
    with tempfile.TemporaryDirectory(prefix="campus-real-chat-") as directory:
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

            def post(url, value):
                response = c.post(
                    url,
                    json=value,
                    headers={**headers, "Idempotency-Key": str(uuid4())},
                )
                assert response.status_code == 200, f"{url}: {response.status_code}"
                return response.json()

            thread = post("/api/agent/threads", {})
            run = post(
                "/api/agent/runs",
                {
                    "thread_id": thread["id"],
                    "message": "明天下午5:30开始参加院运会彩排，持续2小时，请帮我加到课表。"
                    if calendar
                    else "帮我增加一个任务：明天阅读两篇文献，记录关键结论。我没有明确几点截止。",
                },
            )
            deadline = time.monotonic() + 130
            while time.monotonic() < deadline:
                run = c.get(f"/api/agent/runs/{run['id']}").json()
                if run["data"]["status"] in {"done", "failed", "waiting_approval"}:
                    break
                time.sleep(0.2)
            assert run["data"]["status"] == "done", run["data"].get(
                "error", run["data"]["status"]
            )
            events = [
                json.loads(line[6:])
                for line in c.get(
                    f"/api/agent/runs/{run['id']}/events"
                ).text.splitlines()
                if line.startswith("data: ")
            ]
            assert any(
                e["type"] == "tool_started"
                and e["payload"]["name"]
                == (
                    "create_calendar_event_draft"
                    if calendar
                    else "create_assignment_draft"
                )
                for e in events
            )
            deltas = [e for e in events if e["type"] == "message_delta"]
            assert deltas, "Real model produced no streaming text events"
            finals = [
                e
                for e in events
                if e["type"] == "message" and e["payload"]["role"] == "assistant"
            ]
            for final in finals:
                text = "".join(
                    e["payload"]["delta"]
                    for e in deltas
                    if e["payload"]["message_id"] == final["payload"]["message_id"]
                )
                assert text == final["payload"]["content"], (
                    "Partial and final text disagree"
                )
            drafts = c.get("/api/drafts").json()
            assert len(drafts) == 1
            if calendar:
                item = drafts[0]["data"]["payload"]
                assert drafts[0]["data"]["draft_kind"] == "calendar_event"
                a = datetime.fromisoformat(item["starts_at"]).astimezone(
                    ZoneInfo("Asia/Shanghai")
                )
                b = datetime.fromisoformat(item["ends_at"]).astimezone(
                    ZoneInfo("Asia/Shanghai")
                )
                assert (a.hour, a.minute, b.hour, b.minute) == (17, 30, 19, 30)
                assert (b - a).total_seconds() == 7200
                assert c.get("/api/fixed-events").json() == []
            else:
                item = drafts[0]["data"]["payload"]["items"][0]
                assert item["due_at"] is None
                assert item["due_text"] and "明天" in item["due_text"]
            assert c.get("/api/tasks").json() == []
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "source": "real configured model + Deep Agents + official Time MCP",
                        "text_events": len(deltas),
                        "draft": item,
                        "saved_tasks": 0,
                        "reply": [e["payload"]["content"] for e in finals],
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
