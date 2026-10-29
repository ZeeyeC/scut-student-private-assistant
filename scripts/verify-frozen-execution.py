"""Exercise B1 in the actual frozen service using an isolated local profile."""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.launcher import desktop_config, service_identity


def verify(service, extra_checks=None):
    origin = "http://127.0.0.1:5173"
    with httpx.Client(base_url=origin, trust_env=False, timeout=30) as client:
        try:
            client.get("/api/healthz", timeout=1)
        except httpx.ConnectError:
            pass
        else:
            raise RuntimeError("5173 occupied; no service started or data changed")
        with tempfile.TemporaryDirectory(prefix="frozen-execution-") as directory:
            root = Path(directory)
            expected = service_identity(desktop_config(root, root, project=False))
            with (root / "service.log").open("w") as log:
                process = subprocess.Popen(
                    [str(service), "--serve", "--no-browser", "--data-dir", str(root)],
                    cwd=root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    for _ in range(150):
                        if process.poll() is not None:
                            raise RuntimeError("Frozen service exited before startup")
                        try:
                            health = client.get("/api/healthz", timeout=1).json()
                            if any(health.get(k) != v for k, v in expected.items()):
                                raise RuntimeError(
                                    "Service identity mismatch; no writes performed"
                                )
                            assert health["model_configured"] is False
                            break
                        except httpx.ConnectError:
                            time.sleep(0.2)
                    else:
                        raise RuntimeError("Frozen service startup timed out")
                    csrf = client.get("/api/csrf").json()["csrf_token"]

                    def write(path, body, method="POST", key=None):
                        response = client.request(
                            method,
                            "/api" + path,
                            json=body,
                            headers={
                                "Origin": origin,
                                "X-CSRF-Token": csrf,
                                "Idempotency-Key": key or str(uuid4()),
                            },
                        )
                        response.raise_for_status()
                        return response.json() if response.content else None

                    def get(path):
                        response = client.get("/api" + path)
                        response.raise_for_status()
                        return response.json()

                    write("/local/session", {})
                    local_day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                    tomorrow = local_day + timedelta(days=1)
                    draft = write(
                        "/drafts/assignment",
                        {
                            "items": [
                                {
                                    "title": "冻结包执行合成练习",
                                    "due_at": f"{tomorrow}T23:59:00+08:00",
                                }
                            ]
                        },
                    )
                    tid = write(
                        f"/drafts/{draft['id']}/confirm",
                        {"revision": draft["revision"]},
                    )["saved_ids"][0]
                    task = get(f"/tasks/{tid}")
                    draft = write(
                        f"/tasks/{tid}/step-drafts",
                        {
                            "task_revision": task["revision"],
                            "steps": [
                                {
                                    "key": "one",
                                    "title": "合成步骤",
                                    "description": "隔离冻结包检查",
                                    "estimated_minutes": 60,
                                    "dependency_keys": [],
                                    "acceptance_criteria": ["完成"],
                                }
                            ],
                        },
                    )
                    write(
                        f"/drafts/{draft['id']}/confirm",
                        {"revision": draft["revision"]},
                    )
                    draft = write(
                        "/plan-drafts",
                        {"target_date": str(tomorrow), "horizon_days": 1},
                    )
                    write(
                        f"/drafts/{draft['id']}/confirm",
                        {"revision": draft["revision"]},
                    )
                    block = get("/plan-blocks")[0]
                    step = get(f"/tasks/{tid}/steps")[0]
                    task = get(f"/tasks/{tid}")
                    payload = {
                        "client_operation_id": str(uuid4()),
                        "execution_id": str(uuid4()),
                        "task_id": tid,
                        "task_revision": task["revision"],
                        "step_id": step["id"],
                        "step_revision": step["revision"],
                        "plan_block_id": block["id"],
                        "plan_block_revision": block["revision"],
                        "performed_on": str(local_day),
                        "timezone": "Asia/Shanghai",
                        "actual_minutes": 25,
                        "feedback": "partial",
                        "task_status": "open",
                    }
                    record = write("/executions", payload, key="frozen-write")
                    assert write("/executions", payload, key="frozen-write") == record
                    assert write("/executions", payload) == record
                    assert (
                        get(f"/tasks/{tid}/execution-summary")["actual_minutes"] == 25
                    )
                    assert get(f"/tasks/{tid}")["data"]["status"] == "open"
                    current = get("/plan-blocks")[0]
                    assert current["data"]["starts_at"] == block["data"]["starts_at"]
                    assert current["data"]["ends_at"] == block["data"]["ends_at"]
                    write(
                        f"/executions/{record['id']}/corrections",
                        {
                            "client_operation_id": str(uuid4()),
                            "revision": record["revision"],
                            "task_revision": get(f"/tasks/{tid}")["revision"],
                            "actual_minutes": 20,
                            "feedback": "partial",
                        },
                    )
                    assert (
                        get(f"/tasks/{tid}/execution-summary")["actual_minutes"] == 20
                    )
                    assert sorted(
                        r["data"]["actual_minutes"]
                        for r in get(f"/tasks/{tid}/executions")
                    ) == [20, 25]
                    checks = (
                        extra_checks(get, write, tid, local_day) if extra_checks else []
                    )
                    return {
                        "passed": True,
                        "mode": "actual-frozen-service",
                        "data": "isolated-synthetic",
                        "paid_model_calls": 0,
                        "checks": [
                            "identity",
                            "60-minute-plan-kept",
                            "actual25-task-open",
                            "idempotent-retry",
                            "correction20-history25",
                            *checks,
                        ],
                    }
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.service.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
