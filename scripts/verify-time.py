"""Billable real-model probe, synthetic timetable/history in an isolated database."""

import asyncio
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agent import student_agent
from app.config import Config
from app.main import create_app
from app.time_mcp import current_time
from tests.test_agent import ToolModel
from tests.test_foundation import register_login


class OldDateModel(ToolModel):
    """TEST ONLY: reproduce an incorrect old assistant message in the checkpoint."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="TEST ONLY：旧记录错误地认为今天2026年8月30日，明天8月31日。"
                    )
                )
            ]
        )


def main():
    cfg = Config()
    if not cfg.model_api_key or not cfg.text_model:
        raise SystemExit("external_input_required: configure model in the app")
    clock = asyncio.run(current_time("Asia/Shanghai"))
    tomorrow = date.fromisoformat(clock["tomorrow"])
    with tempfile.TemporaryDirectory(prefix="campus-real-time-") as directory:
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

            def post(path, value):
                r = c.post(
                    path, json=value, headers={**h, "Idempotency-Key": str(uuid4())}
                )
                assert r.status_code == 200, f"{path}: {r.status_code}"
                return r.json()

            settings = c.get("/api/settings").json()
            settings["data"].update(
                timezone="Asia/Shanghai",
                week1_monday=(
                    tomorrow - timedelta(days=tomorrow.weekday())
                ).isoformat(),
                periods={"1": {"start": "08:00:00", "end": "08:45:00"}},
            )
            assert (
                c.put(
                    "/api/settings",
                    json=settings,
                    headers={**h, "Idempotency-Key": "settings"},
                ).status_code
                == 200
            )
            draft = post(
                "/api/drafts/timetable",
                {
                    "semester_label": "虚构时间验收学期",
                    "courses": [
                        {
                            "source_key": "time-probe",
                            "name": "虚构时间验收课程",
                            "weekday": tomorrow.isoweekday(),
                            "weeks": [1],
                            "periods": [1],
                            "location": "测试教室",
                        }
                    ],
                },
            )
            post(f"/api/drafts/{draft['id']}/confirm", {"revision": draft["revision"]})
            thread = post("/api/agent/threads", {})
            c.app.state.agent_model_factory = lambda: OldDateModel()

            def run(message):
                import time

                r = post(
                    "/api/agent/runs", {"thread_id": thread["id"], "message": message}
                )
                deadline = time.monotonic() + 130
                while time.monotonic() < deadline:
                    r = c.get(f"/api/agent/runs/{r['id']}").json()
                    if r["data"]["status"] in {"done", "failed", "waiting_approval"}:
                        assert r["data"]["status"] == "done", r["data"].get(
                            "error", r["data"]["status"]
                        )
                        return r
                    time.sleep(0.2)
                raise AssertionError("Model timeout")

            run("生成一条明确标注为测试的旧日期错误记录")
            del c.app.state.agent_model_factory
            run("明天有什么课？")
            graph = student_agent(c.app, c.get("/api/me").json()["id"])
            snapshot = c.portal.call(
                graph.aget_state,
                {"configurable": {"thread_id": thread["id"]}},
            )
            messages = snapshot.values["messages"]
            calls = [
                call
                for m in messages
                if isinstance(m, AIMessage)
                for call in m.tool_calls
            ]
            assert any(x["name"] == "get_current_time" for x in calls), (
                "Real model did not call Time MCP tool"
            )
            assert any(
                x["name"] == "list_course_occurrences"
                and x["args"]
                == {
                    "start_date": tomorrow.isoformat(),
                    "end_date": tomorrow.isoformat(),
                }
                for x in calls
            ), "Real model queried wrong local date"
            final = next(
                m for m in reversed(messages) if isinstance(m, AIMessage) and m.content
            )
            assert "虚构时间验收课程" in str(final.content)
            assert c.get("/api/tasks").json() == []
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "source": "real model + official MCP + Deep Agents",
                        "today": clock["today"],
                        "tomorrow": tomorrow.isoformat(),
                        "reply": final.content,
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
