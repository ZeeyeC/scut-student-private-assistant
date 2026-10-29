"""Check B interaction routes in the actual binary, with synthetic local data."""

import argparse
import hashlib
import importlib.util
import json
from datetime import timedelta
from pathlib import Path


def verify(service):
    spec = importlib.util.spec_from_file_location(
        "b_interaction_harness", Path(__file__).with_name("verify-frozen-execution.py")
    )
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    def checks(get, write, task_id, local_day):
        assert "b-interaction-v1" in get("/healthz")["capabilities"]
        before = get("/plan-blocks")
        tomorrow = local_day + timedelta(days=1)
        intent = write(
            "/constraint-intents", {"data": {"day_expression": str(tomorrow)}}
        )
        assert intent["data"]["clarifications"] and intent["draft"] is None
        intent = write(
            f"/constraint-intents/{intent['id']}",
            {
                "revision": intent["revision"],
                "changes": {"start_time": "14:00", "end_time": "17:00"},
            },
            "PATCH",
        )
        intent = write(
            f"/constraint-intents/{intent['id']}/prepare",
            {"revision": intent["revision"]},
        )
        assert get("/scheduling-constraints") == []
        draft = intent["draft"]
        write(f"/drafts/{draft['id']}/confirm", {"revision": draft["revision"]})
        restored = get(f"/constraint-intents/{intent['id']}")
        assert restored["data"]["status"] == "confirmed"
        rule = restored["constraint"]
        write(
            f"/scheduling-constraints/{rule['id']}",
            {"revision": rule["revision"], "active": False},
            "PATCH",
        )
        assert (
            get(f"/constraint-intents/{intent['id']}")["data"]["status"] == "disabled"
        )
        assert get("/plan-blocks") == before
        cfg = get("/settings")
        negotiation = write(
            "/planning-intents",
            {
                "source_revision": cfg["revision"],
                "data": {
                    "description": "冻结包合成协商",
                    "target_date": str(tomorrow),
                    "horizon_days": 1,
                    "timezone": "Asia/Shanghai",
                    "protected_intervals": [],
                    "preferred_intervals": [],
                    "keep_block_ids": [],
                    "reduced_daily_limit_minutes": None,
                },
            },
        )
        negotiation = write(
            f"/planning-intents/{negotiation['id']}/preview",
            {
                "revision": negotiation["revision"],
                "source_revision": cfg["revision"],
            },
        )
        assert negotiation["data"]["preview"]["options"]
        chosen = write(
            f"/planning-intents/{negotiation['id']}/choose",
            {
                "revision": negotiation["revision"],
                "source_revision": cfg["revision"],
                "option_id": negotiation["data"]["preview"]["options"][0]["id"],
            },
        )
        assert (
            chosen["draft"]["data"]["status"] == "pending"
            and get("/plan-blocks") == before
        )
        write(
            f"/drafts/{chosen['draft']['id']}/confirm",
            {"revision": chosen["draft"]["revision"]},
        )
        confirmed = get("/plan-blocks")
        write(
            f"/planning-intents/{negotiation['id']}/cancel",
            {
                "revision": chosen["intent"]["revision"],
                "source_revision": get("/settings")["revision"],
            },
        )
        assert get("/plan-blocks") == confirmed
        capacity = get("/goal-capacity")
        assert (
            capacity["shared_capacity_upper_bound_minutes"] >= 0
            and capacity["actual_minutes"] is None
        )
        monday = local_day - timedelta(days=local_day.weekday())
        report = get(f"/weekly-review?week_start={monday}&timezone=Asia%2FShanghai")
        write(
            "/weekly-review/actions",
            {
                "week_start": str(monday),
                "timezone": "Asia/Shanghai",
                "revision": report["review"]["revision"],
                "source_revision": report["source_revision"],
                "reason": "核对下周已确认事实",
                "action": "accept",
            },
        )
        report = get(f"/weekly-review?week_start={monday}&timezone=Asia%2FShanghai")
        next_week = write(
            "/weekly-review/plan-draft",
            {
                "week_start": str(monday),
                "timezone": "Asia/Shanghai",
                "revision": report["review"]["revision"],
                "source_revision": report["source_revision"],
            },
        )
        assert (
            next_week["draft"]["data"]["status"] == "pending"
            and get("/plan-blocks") == confirmed
        )
        prefs = get("/proactive/preferences")
        assert prefs["data"]["enabled"] is False
        write(
            "/proactive/preferences",
            {
                "revision": prefs["revision"],
                "data": {
                    **prefs["data"],
                    "enabled": True,
                    "timezone": "Asia/Shanghai",
                    "quiet_hours": [],
                },
            },
            "PUT",
        )
        suggestions = write("/proactive/refresh", {"app_active": True})
        matching = [
            s
            for s in suggestions["suggestions"]
            if s["data"].get("task_id") == task_id and s["data"]["state"] == "pending"
        ]
        assert matching
        suggestion = matching[0]
        details = write(
            f"/proactive/suggestions/{suggestion['id']}/actions",
            {
                "revision": suggestion["revision"],
                "fingerprint": suggestion["data"]["fingerprint"],
                "action": "accept",
                "accept_mode": "details",
            },
        )
        assert (
            details["open_task_id"] == task_id
            and get(f"/tasks/{task_id}")["data"]["status"] == "open"
        )
        duration = get("/duration-suggestions")
        assert (
            duration["generation_status"] == "ready"
            and duration["suggestions"] == []
        )
        return [
            "b-interaction-capability",
            "unknown-clock-clarification",
            "same-intent-original-constraint-draft",
            "confirmed-rule-restored-and-explicitly-disabled",
            "negotiation-original-plan-review",
            "cancel-preserves-confirmed-schedule",
            "shared-goal-capacity",
            "weekly-original-next-week-draft",
            "proactive-opt-in-real-risk-and-owned-task-details",
            "duration-generator-honestly-unavailable",
        ]

    result = harness.verify(service, checks)
    result["service_sha256"] = hashlib.sha256(service.read_bytes()).hexdigest()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.service.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
