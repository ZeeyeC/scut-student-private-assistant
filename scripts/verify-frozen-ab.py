"""Verify real A planner reads B's corrected execution projection in the App."""

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path


def module(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(filename)
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def verify(service):
    b = module("independent_verifier", "verify-frozen-independent.py")
    harness = module("execution_verifier", "verify-frozen-execution.py")

    def checks(get, write, task_id, local_day):
        verified = b.independent_checks(get, write, task_id, local_day)
        # B has left an effective corrected20 + new manual25, with estimate60.
        before = get("/plan-blocks")
        capacity = get("/planning-capacity?horizon_days=7")
        assert capacity["required_minutes"] == 15
        assert capacity["proposed_minutes"] == 15
        options = get("/planning-options?horizon_days=7")
        assert len(options["options"]) == 2
        assert all(o["proposed_minutes"] == 15 for o in options["options"])
        assert options["profile_integration"] == "pending_person_b"
        assert options["goal_integration"] == "pending_person_b"
        repair = get("/replanning?horizon_days=7")
        seconds = sum(
            (
                datetime.fromisoformat(row["ends_at"])
                - datetime.fromisoformat(row["starts_at"])
            ).total_seconds()
            for row in repair["added"]
        )
        assert seconds == 15 * 60
        assert repair["execution_integration"] == "pending_person_b"
        assert get("/planning-risks?horizon_days=7")["required_minutes"] == 15
        assert get("/plan-blocks") == before
        return [
            *verified,
            "real-B-actual45-to-A-remaining15",
            "two-real-options-use-corrected-remaining15",
            "replanning-and-risk-read-real-execution-projection",
            "profile-goal-consumers-still-honestly-pending",
            "cross-domain-queries-preserve-schedule",
        ]

    result = harness.verify(service, checks)
    with service.open("rb") as stream:
        result["service_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
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
