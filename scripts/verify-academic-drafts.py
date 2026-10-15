"""Billable real-model check. Synthetic tasks in a temporary database only."""

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--calendar-boundary", action="store_true")
    calendar_boundary = parser.parse_args().calendar_boundary
    cfg = Config()
    if not cfg.model_api_key or not cfg.text_model:
        raise SystemExit("external_input_required: configure text model")
    with tempfile.TemporaryDirectory(prefix="campus-academic-real-") as directory:
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
            h = register_login(c)

            def write(url, body, method="POST"):
                r = c.request(
                    method,
                    url,
                    json=body,
                    headers={**h, "Idempotency-Key": str(uuid4())},
                )
                assert r.status_code == 200, (url, r.status_code)
                return r.json()

            settings = c.get("/api/settings").json()
            settings["data"]["week1_monday"] = "2026-08-31"
            write("/api/settings", settings, "PUT")
            thread = write("/api/agent/threads", {})

            def ask(message):
                r = write(
                    "/api/agent/runs", {"thread_id": thread["id"], "message": message}
                )
                until = time.monotonic() + 130
                while time.monotonic() < until:
                    r = c.get(f"/api/agent/runs/{r['id']}").json()
                    if r["data"]["status"] in {"done", "failed", "waiting_approval"}:
                        break
                    time.sleep(0.2)
                assert r["data"]["status"] == "done", r["data"].get(
                    "error", r["data"]["status"]
                )
                events = [
                    json.loads(line[6:])
                    for line in c.get(
                        f"/api/agent/runs/{r['id']}/events"
                    ).text.splitlines()
                    if line.startswith("data: ")
                ]
                return [
                    e["payload"]["name"] for e in events if e["type"] == "tool_started"
                ]

            if calendar_boundary:
                names = ask("帮我增加一个待办：11月1日之前完成日期边界验收报告。")
                drafts = c.get("/api/drafts").json()
                assert len(drafts) == 1, len(drafts)
                item = drafts[0]["data"]["payload"]["items"][0]
                year = datetime.now(ZoneInfo("Asia/Shanghai")).year
                expected = datetime(year, 11, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
                assert "create_assignment_draft" in names, names
                assert (
                    item["due_at"]
                    and datetime.fromisoformat(item["due_at"]) == expected
                ), item
                assert "due_at" not in item["uncertain_fields"]
                assert c.get("/api/tasks").json() == []
                d = drafts[0]
                write(f"/api/drafts/{d['id']}/confirm", {"revision": d["revision"]})
                assert len(c.get("/api/tasks").json()) == 1
                print(
                    json.dumps(
                        {
                            "status": "PASS",
                            "source": "real configured model + Deep Agents + official Time MCP",
                            "tools": names,
                            "date_boundary": item["due_at"],
                            "draft_saved_without_manual_date_entry": True,
                            "data": "synthetic temporary database only",
                        },
                        ensure_ascii=False,
                    )
                )
                return

            created_tools = ask(
                "第14周之前我要完成C++大作业，11周之前要完成agent大作业，帮我添加到待办事项。"
            )
            drafts = c.get("/api/drafts").json()
            assert len(drafts) == 2, len(drafts)
            cpp = next(
                d for d in drafts if "C++" in d["data"]["payload"]["items"][0]["title"]
            )
            other = next(d for d in drafts if d["id"] != cpp["id"])
            assert (
                cpp["data"]["payload"]["items"][0]["due_at"]
                == "2026-11-30T00:00:00+08:00"
            )
            assert (
                other["data"]["payload"]["items"][0]["due_at"]
                == "2026-11-09T00:00:00+08:00"
            )
            assert c.get("/api/tasks").json() == []
            expected = (
                datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=1)
            ).date()
            edited_tools = ask("把 C++ 大作业草稿的截止时间改成明天晚上8点。")
            assert {
                "get_current_time",
                "list_assignment_drafts",
                "set_assignment_draft_deadline",
            } <= set(edited_tools), edited_tools
            edited = c.get(f"/api/drafts/{cpp['id']}").json()
            assert edited["revision"] == cpp["revision"] + 1
            target = datetime.fromisoformat(
                edited["data"]["payload"]["items"][0]["due_at"]
            ).astimezone(ZoneInfo("Asia/Shanghai"))
            assert target.date() == expected and (target.hour, target.minute) == (20, 0)
            assert len(c.get("/api/drafts").json()) == 2
            assert c.get("/api/tasks").json() == []
            for d in [edited, other]:
                write(f"/api/drafts/{d['id']}/confirm", {"revision": d["revision"]})
            assert len(c.get("/api/tasks").json()) == 2
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "source": "real configured model + Deep Agents + official Time MCP",
                        "create_tools": created_tools,
                        "edit_tools": edited_tools,
                        "initial_boundaries": [
                            "2026-11-30T00:00+08:00",
                            "2026-11-09T00:00+08:00",
                        ],
                        "edited_deadline": target.isoformat(),
                        "same_draft_id": True,
                        "independent_saves": 2,
                        "data": "synthetic temporary database only",
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
