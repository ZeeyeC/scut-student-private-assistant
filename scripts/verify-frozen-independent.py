"""Verify independent B features in the real frozen binary, with isolated data."""

import argparse
import hashlib
import importlib.util
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx


def independent_checks(get, write, task_id, local_day):
    # The shared B1 harness has already left a corrected 20-minute fact.
    task = get(f"/tasks/{task_id}")
    step = get(f"/tasks/{task_id}/steps")[0]
    timer = write(
        "/execution-timers",
        {
            "client_operation_id": str(uuid4()),
            "execution_id": str(uuid4()),
            "task_id": task_id,
            "task_revision": task["revision"],
            "step_id": step["id"],
            "step_revision": step["revision"],
            "performed_on": str(local_day),
            "timezone": "Asia/Shanghai",
            "legacy_resolution": "separate",
        },
    )
    for action in ("pause", "resume"):
        timer = write(
            f"/execution-timers/{timer['id']}/actions",
            {
                "revision": timer["revision"],
                "client_operation_id": str(uuid4()),
                "action": action,
            },
        )
    payload = {
        "revision": timer["revision"],
        "client_operation_id": str(uuid4()),
        "action": "finish",
        "feedback": "partial",
        "unfinished_reason": "insufficient_time",
        "actual_minutes": 25,
        "task_status": "open",
        "task_revision": get(f"/tasks/{task_id}")["revision"],
    }
    try:
        write(
            f"/execution-timers/{timer['id']}/actions",
            {**payload, "feedback": "skipped", "actual_minutes": 5},
        )
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 422
    else:
        raise AssertionError("Invalid skipped/manual minutes must return422")
    settings = get("/settings")
    original_timezone = settings["data"]["timezone"]
    settings["data"]["timezone"] = "UTC"
    write("/settings", settings, method="PUT")
    result = write(f"/execution-timers/{timer['id']}/actions", payload, key="finish")
    assert (
        write(f"/execution-timers/{timer['id']}/actions", payload, key="finish")
        == result
    )
    assert get(f"/tasks/{task_id}/execution-summary")["actual_seconds"] == 2700
    assert len(get(f"/tasks/{task_id}/executions")) == 3
    assert get(f"/tasks/{task_id}")["data"]["status"] == "open"
    records = get(f"/tasks/{task_id}/executions")
    assert all(r["data"]["timezone"] == original_timezone for r in records)
    settings = get("/settings")
    settings["data"]["timezone"] = original_timezone
    write("/settings", settings, method="PUT")

    profile = get("/profile")
    assert profile["data"]["preferences"]["focus_minutes"] is None
    profile = write(
        "/profile",
        {
            "revision": profile["revision"],
            "data": {
                "timezone": "Asia/Shanghai",
                "preferences": {"focus_minutes": 45, "break_minutes": 0},
            },
        },
        method="PUT",
    )
    assert profile["data"]["preferences"]["break_minutes"] == 0
    profile = write("/profile/reset", {"revision": profile["revision"]})
    assert profile["data"]["preferences"]["focus_minutes"] is None
    assert len(get("/tasks")) == 1

    goal = write(
        "/goals",
        {
            "title": "冻结包合成目标",
            "weekly_budget_minutes": 600,
            "priority": 3,
            "load_category": "study",
            "allowed_adjustment": "reduce",
            "subtasks": [
                {
                    "title": "已完成合成练习",
                    "estimated_minutes": 30,
                    "status": "completed",
                    "task_id": task_id,
                }
            ],
        },
    )
    goal = write(
        f"/goals/{goal['id']}",
        {"revision": goal["revision"], "paused": True},
        method="PATCH",
    )
    assert goal["data"]["paused"] is True
    assert len(goal["data"]["completion_history"]) == 1
    assert goal["capacity"]["weekly_available_minutes"] is None
    assert goal["arrangements"] == []

    monday = local_day - timedelta(days=local_day.weekday())
    before = get("/plan-blocks")
    report = get(f"/weekly-review?week_start={monday}&timezone=Asia%2FShanghai")
    assert report["execution"]["actual_seconds"] == 2700
    write(
        "/weekly-review/actions",
        {
            "week_start": str(monday),
            "timezone": "Asia/Shanghai",
            "revision": report["review"]["revision"],
            "source_revision": report["source_revision"],
            "action": "accept",
            "reason": "下一周分两次练习，等待核对容量后安排。",
        },
    )
    report = get(f"/weekly-review?week_start={monday}&timezone=Asia%2FShanghai")
    assert report["review"]["data"]["status"] == "accepted_pending_integration"
    assert get("/plan-blocks") == before
    return [
        "timer-pause-resume-manual25-once",
        "invalid-manual-finish422-remains-editable",
        "finish-keeps-original-timezone-after-settings-change",
        "corrected20-plus-manual25-pooled45",
        "profile-zero-and-reset-preserve-task",
        "paused-goal-keeps-completion-capacity-unknown",
        "weekly45-and-pending-intent-preserves-plan",
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "frozen_execution", Path(__file__).with_name("verify-frozen-execution.py")
    )
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    result = harness.verify(args.service.resolve(), independent_checks)
    with args.service.open("rb") as stream:
        result["service_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
