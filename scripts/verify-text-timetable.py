"""Opt-in paid two-turn chat probe using generated courses and temporary data.

Reads only model settings from the supplied private file. Does not read personal
databases, upload files, save a course or print credentials/provider responses.
Not called by release-macos.py or the automated test suite.
"""

import argparse
import json
import sys
import tempfile
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.calendar import parse_week_expression
from app.main import create_app
from dotenv import dotenv_values
from fastapi.testclient import TestClient


def verify(settings_file):
    private = dotenv_values(settings_file)
    model_fields = {
        "model_provider",
        "model_base_url",
        "model_api_key",
        "text_model",
        "vision_model",
        "model_use_system_proxy",
    }
    model = {
        k.lower(): v
        for k, v in private.items()
        if k.lower() in model_fields and v is not None
    }
    if not model.get("model_api_key"):
        raise ValueError("Model not configured")
    with tempfile.TemporaryDirectory(prefix="campus-text-real-") as temporary:
        root = Path(temporary)
        app = create_app(
            {
                **model,
                "app_mode": "shared",
                "settings_file": str(root / "model.env"),
                "database_url": f"sqlite+aiosqlite:///{root}/test.db",
                "agent_db_path": str(root / "agent.db"),
                "upload_dir": str(root / "uploads"),
                "public_origin": "http://testserver",
                "secure_cookie": False,
                "scut_adapter_path": "",
            }
        )
        with TestClient(app) as c:
            token = c.get("/api/csrf").json()["csrf_token"]
            h = {"Origin": "http://testserver", "X-CSRF-Token": token}

            def write(path, payload, method="post"):
                response = getattr(c, method)(
                    "/api" + path,
                    json=payload,
                    headers={**h, "Idempotency-Key": str(uuid4())},
                )
                response.raise_for_status()
                return response.json()

            assert (
                c.post(
                    "/api/auth/register",
                    json={
                        "email": "synthetic@example.com",
                        "password": "Synthetic!Password2026",
                    },
                    headers=h,
                ).status_code
                == 201
            )
            assert (
                c.post(
                    "/api/auth/login",
                    data={
                        "username": "synthetic@example.com",
                        "password": "Synthetic!Password2026",
                    },
                    headers=h,
                ).status_code
                == 204
            )
            settings = c.get("/api/settings").json()
            settings["data"].update(
                semester_name="2026秋季",
                week1_monday="2026-09-07",
                periods={
                    "1": {"start": "08:00", "end": "08:45"},
                    "2": {"start": "08:50", "end": "09:35"},
                },
            )
            write("/settings", settings, "put")
            tid = write("/agent/threads", {})["id"]

            def chat(message):
                run = write("/agent/runs", {"thread_id": tid, "message": message})
                deadline = time.monotonic() + 130
                while time.monotonic() < deadline:
                    state = c.get("/api/agent/runs/" + run["id"]).json()["data"][
                        "status"
                    ]
                    if state in {"done", "failed", "waiting_approval"}:
                        assert state == "done", "Agent run did not complete"
                        return
                    time.sleep(0.3)
                raise TimeoutError("Agent probe timed out")

            chat(
                "请在课表里添加高等数学：每周一第1、2节，周次暂时还不知道。请生成课表草稿并问我缺少的周次，不要保存课程。"
            )
            drafts = c.get("/api/drafts").json()
            assert (
                len(drafts) == 1 and drafts[0]["data"]["draft_kind"] == "timetable_text"
            )
            original = drafts[0]
            course = original["data"]["payload"]["candidates"][0]
            assert (
                course["name"] == "高等数学"
                and course["weekday"] == 1
                and course["periods"] == [1, 2]
            )
            assert course["weeks_text"] is None
            assert any(
                q["field"] == "weeks_text" for q in original["data"]["clarifications"]
            )
            chat(
                "这门高等数学是第3至8周，其他信息不变，请补充原草稿，不要新建，也不要保存正式课表。"
            )
            drafts = c.get("/api/drafts").json()
            assert len(drafts) == 1 and drafts[0]["id"] == original["id"]
            course = drafts[0]["data"]["payload"]["candidates"][0]
            try:
                assert parse_week_expression(course["weeks_text"], 20) == [
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                ]
            except (ValueError, AssertionError) as exc:
                exc.synthetic_week_expression = course["weeks_text"]
                raise
            assert course["weekday"] == 1 and course["periods"] == [1, 2]
            assert c.get("/api/courses").json() == []
            return [
                "real model selected course draft tool",
                "unknown weeks preserved and questioned",
                "follow-up patched original draft",
                "other fields preserved",
                "no formal course saved",
            ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        checks = verify(args.settings_file)
        result = {"passed": True, "checks": checks}
    except Exception as exc:  # noqa: BLE001 -- never include provider response or inputs
        result = {
            "passed": False,
            "error_type": type(exc).__name__,
            "locations": [
                {
                    "file": Path(frame.filename).name,
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in traceback.extract_tb(exc.__traceback__)[-8:]
            ],
            "synthetic_week_expression": getattr(
                exc, "synthetic_week_expression", None
            ),
        }
    result.update(
        timestamp=datetime.now(UTC).isoformat(),
        scope="two real agent turns, generated synthetic course, temporary profile",
        personal_data_sent=False,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
