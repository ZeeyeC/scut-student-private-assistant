"""Check the packaged PDF decoder using an isolated temporary local profile.

Refuses an occupied port and verifies database identity before any API writes.
No personal files or model calls. Stops only the child process it created.
"""

import argparse
import http.cookiejar
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.launcher import desktop_config, service_identity
from pypdf import PdfWriter


def verify(service):
    origin = "http://127.0.0.1:5173"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    try:
        opener.open(origin + "/api/healthz", timeout=1)
    except urllib.error.HTTPError:
        raise SystemExit("5173 occupied; nothing started or changed.") from None
    except urllib.error.URLError:
        pass
    else:
        raise SystemExit("5173 occupied; nothing started or changed.")
    with tempfile.TemporaryDirectory(prefix="campus-frozen-pdf-") as temporary:
        root = Path(temporary)
        expected = service_identity(desktop_config(root, root, project=False))
        with (root / "server.log").open("w") as log:
            process = subprocess.Popen(
                [str(service), "--serve", "--no-browser", "--data-dir", str(root)],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Frozen backend startup failed; temporary log retained only until exit."
                        )
                    try:
                        health = json.load(
                            opener.open(origin + "/api/healthz", timeout=1)
                        )
                        if any(health.get(k) != v for k, v in expected.items()):
                            raise RuntimeError(
                                "Different service identity; no writes performed."
                            )
                        assert health["model_configured"] is False
                        assert "timetable-recognition" in health["capabilities"]
                        assert "timetable-text" in health["capabilities"]
                        assert "planning-today" in health["capabilities"]
                        assert "course-changes" in health["capabilities"]
                        break
                    except urllib.error.URLError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Frozen backend did not start.")
                csrf = json.load(opener.open(origin + "/api/csrf"))["csrf_token"]

                def request(path, body, content_type="application/json", method="POST"):
                    headers = {
                        "Origin": origin,
                        "X-CSRF-Token": csrf,
                        "Idempotency-Key": str(uuid4()),
                        "Content-Type": content_type,
                    }
                    return opener.open(
                        urllib.request.Request(
                            origin + "/api" + path,
                            data=body,
                            headers=headers,
                            method=method,
                        ),
                        timeout=30,
                    )

                request("/local/session", b"{}").read()

                def write_json(path, body, method="POST"):
                    return json.load(
                        request(path, json.dumps(body).encode(), method=method)
                    )

                # Exercise new domain modules inside the actual PyInstaller binary.
                local_day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                settings = json.load(opener.open(origin + "/api/settings"))
                settings["data"].update(
                    timezone="Asia/Shanghai",
                    week1_monday=(
                        local_day - timedelta(days=local_day.weekday())
                    ).isoformat(),
                    periods={
                        "1": {"start": "09:00", "end": "09:40"},
                        "2": {"start": "10:00", "end": "10:40"},
                        "3": {"start": "11:00", "end": "11:40"},
                    },
                )
                write_json("/settings", settings, "PUT")
                course_draft = write_json(
                    "/drafts/timetable",
                    {
                        "semester_label": "synthetic frozen check",
                        "courses": [
                            {
                                "source_key": "frozen-course",
                                "name": "冻结包合成课程",
                                "weekday": local_day.isoweekday(),
                                "weeks": [1, 2],
                                "periods": [1, 3],
                            }
                        ],
                    },
                )
                saved = write_json(
                    f"/drafts/{course_draft['id']}/confirm",
                    {"revision": course_draft["revision"]},
                )
                cid = saved["saved_ids"][0]
                query = f"/api/occurrences?start={local_day}&end={local_day + timedelta(days=1)}"
                original = json.load(opener.open(origin + query))
                assert len(original[0]["teaching_intervals"]) == 2
                assert original[0]["break_intervals"] == []
                agenda_query = f"/api/calendar-events?start={local_day}&end={local_day}"
                split_events = json.load(opener.open(origin + agenda_query))["events"]
                assert len(split_events) == 2
                assert split_events[1]["id"] == original[0]["id"] + ":period-3"
                tomorrow = local_day + timedelta(days=1)
                for action in ("move", "cancel", "restore"):
                    payload = {
                        "course_id": cid,
                        "original_date": local_day.isoformat(),
                        "action": action,
                        "reason": "合成测试通知",
                    }
                    if action == "move":
                        payload.update(
                            starts_at=f"{tomorrow}T10:00:00+08:00",
                            ends_at=f"{tomorrow}T11:00:00+08:00",
                        )
                    draft = write_json("/drafts/course-change", payload)
                    write_json(
                        f"/drafts/{draft['id']}/confirm",
                        {"revision": draft["revision"]},
                    )
                    events = json.load(opener.open(origin + query))
                    if action == "move":
                        assert events[0]["starts_at"].startswith(str(tomorrow))
                    elif action == "cancel":
                        assert events == []
                    else:
                        assert events == original
                assert (
                    len(json.load(opener.open(origin + "/api/course-change-history")))
                    == 3
                )
                plan = write_json("/plan-drafts", {"scope": "today"})
                assert plan["data"]["payload"]["target_date"] == str(local_day)
                assert plan["data"]["payload"]["horizon_days"] == 1
                assert json.load(opener.open(origin + "/api/plan-blocks")) == []
                # Verify the actual frozen planner uses the gap, with no model.
                future = local_day + timedelta(days=7)
                task_draft = write_json(
                    "/drafts/assignment",
                    {
                        "items": [
                            {
                                "title": "冻结包空档练习",
                                "due_at": f"{future}T12:00:00+08:00",
                            }
                        ]
                    },
                )
                saved_task = write_json(
                    f"/drafts/{task_draft['id']}/confirm",
                    {"revision": task_draft["revision"]},
                )
                tid = saved_task["saved_ids"][0]
                task = json.load(opener.open(origin + f"/api/tasks/{tid}"))
                step_draft = write_json(
                    f"/tasks/{tid}/step-drafts",
                    {
                        "task_revision": task["revision"],
                        "steps": [
                            {
                                "key": "a",
                                "title": "合成练习",
                                "description": "验证冻结包空档",
                                "estimated_minutes": 30,
                                "dependency_keys": [],
                                "acceptance_criteria": ["完成"],
                            }
                        ],
                    },
                )
                write_json(
                    f"/drafts/{step_draft['id']}/confirm",
                    {"revision": step_draft["revision"]},
                )
                gap_plan = write_json(
                    "/plan-drafts", {"target_date": str(future), "horizon_days": 1}
                )
                payload = gap_plan["data"]["payload"]
                assert payload["rule_version"] == "personal-facts-1"
                assert len(payload["blocks"]) == 1
                block = payload["blocks"][0]
                assert datetime.fromisoformat(
                    block["starts_at"]
                ) == datetime.fromisoformat(f"{future}T09:50:00+08:00")
                assert datetime.fromisoformat(
                    block["ends_at"]
                ) == datetime.fromisoformat(f"{future}T10:20:00+08:00")
                capacity_before = json.load(opener.open(origin + "/api/data-export"))[
                    "resources"
                ]
                capacity_query = (
                    f"/api/planning-capacity?target_date={future}&horizon_days=1"
                )
                capacity = json.load(opener.open(origin + capacity_query))
                assert (
                    capacity["required_minutes"] == capacity["proposed_minutes"] == 30
                )
                assert capacity["unallocated_minutes"] == 0
                assert (
                    capacity["days"][0]["free_windows"]
                    == payload["capacity"]["days"][0]["free_windows"]
                )
                assert (
                    json.load(opener.open(origin + "/api/data-export"))["resources"]
                    == capacity_before
                )
                write_json(
                    f"/drafts/{gap_plan['id']}/confirm",
                    {"revision": gap_plan["revision"]},
                )
                assert len(json.load(opener.open(origin + "/api/plan-blocks"))) == 1
                weekly_draft = write_json(
                    "/drafts/scheduling-constraint",
                    {
                        "constraint": {
                            "title": "冻结包每周固定安排",
                            "strength": "hard",
                            "recurrence": "weekly",
                            "timezone": "Asia/Shanghai",
                            "starts_at": f"{local_day}T09:40:00+08:00",
                            "ends_at": f"{local_day}T11:00:00+08:00",
                            "weekdays": [local_day.isoweekday()],
                            "valid_until": str(future),
                        }
                    },
                )
                weekly_preview = write_json(
                    f"/drafts/{weekly_draft['id']}/constraint-preview?start={future}&end={future}",
                    {
                        "revision": weekly_draft["revision"],
                        "payload": weekly_draft["data"]["payload"],
                    },
                )
                assert len(weekly_preview["windows"]) == 1
                assert len(weekly_preview["affected_plans"]) == 1
                assert (
                    json.load(opener.open(origin + "/api/scheduling-constraints")) == []
                )
                weekly_saved = write_json(
                    f"/drafts/{weekly_draft['id']}/confirm",
                    {"revision": weekly_draft["revision"]},
                )
                weekly_id = weekly_saved["saved_ids"][0]
                weekly_plan = write_json(
                    "/plan-drafts", {"target_date": str(future), "horizon_days": 1}
                )["data"]["payload"]
                assert weekly_plan["blocks"] == []
                assert weekly_plan["protected_windows"][0]["constraint_id"] == weekly_id
                assert weekly_plan["unscheduled"][0]["remaining_minutes"] == 30
                capacity = json.load(opener.open(origin + capacity_query))
                assert capacity["proposed_minutes"] == 0
                # Afternoon remains free, but the task is due at noon. Capacity
                # upper bound must not be confused with feasible task minutes.
                assert capacity["capacity_upper_bound_minutes"] > 0
                assert (
                    capacity["capacity_upper_bound_minutes"]
                    == weekly_plan["capacity"]["capacity_upper_bound_minutes"]
                )
                assert capacity["unallocated_minutes"] == 30
                assert len(json.load(opener.open(origin + "/api/plan-blocks"))) == 1
                before_repair = json.load(opener.open(origin + "/api/data-export"))[
                    "resources"
                ]
                repair_report = json.load(
                    opener.open(
                        origin + f"/api/replanning?target_date={future}&horizon_days=1"
                    )
                )
                assert repair_report["needs_changes"]
                assert repair_report["removed"][0]["id"] == block["id"]
                assert repair_report["unallocated_minutes"] == 30
                assert (
                    json.load(opener.open(origin + "/api/data-export"))["resources"]
                    == before_repair
                )
                repair_body = {"target_date": str(future), "horizon_days": 1}
                repair_draft = write_json("/replan-drafts", repair_body)
                assert (
                    write_json("/replan-drafts", repair_body)["id"]
                    == repair_draft["id"]
                )
                assert len(json.load(opener.open(origin + "/api/plan-blocks"))) == 1
                receipt = write_json(
                    f"/drafts/{repair_draft['id']}/confirm",
                    {"revision": repair_draft["revision"]},
                )
                assert (
                    write_json(
                        f"/drafts/{repair_draft['id']}/confirm",
                        {"revision": repair_draft["revision"]},
                    )
                    == receipt
                )
                assert json.load(opener.open(origin + "/api/plan-blocks")) == []
                write_json(
                    f"/scheduling-constraints/{weekly_id}",
                    {"revision": 1, "active": False},
                    "PATCH",
                )
                soft = write_json(
                    "/drafts/scheduling-constraint",
                    {
                        "constraint": {
                            "title": "明确空档偏好",
                            "strength": "soft",
                            "timezone": "Asia/Shanghai",
                            "starts_at": f"{future}T09:50:00+08:00",
                            "ends_at": f"{future}T10:20:00+08:00",
                        }
                    },
                )
                write_json(
                    f"/drafts/{soft['id']}/confirm", {"revision": soft["revision"]}
                )
                before_options = json.load(opener.open(origin + "/api/data-export"))[
                    "resources"
                ]
                options = json.load(
                    opener.open(
                        origin
                        + f"/api/planning-options?target_date={future}&horizon_days=1"
                    )
                )
                assert len(options["options"]) == 2 and options["preference_count"] == 1
                assert options["options"][1]["preferred_minutes"] == 30
                risks = json.load(
                    opener.open(
                        origin
                        + f"/api/planning-risks?target_date={future}&horizon_days=1"
                    )
                )
                assert risks["unallocated_minutes"] == 0
                assert (
                    json.load(opener.open(origin + "/api/data-export"))["resources"]
                    == before_options
                )
                preferred = write_json(
                    "/plan-drafts",
                    {
                        "target_date": str(future),
                        "horizon_days": 1,
                        "strategy": "preferred",
                        "expected_source_revision": options["source_revision"],
                    },
                )
                assert preferred["data"]["payload"]["planning_strategy"] == "preferred"
                write_json(
                    f"/drafts/{preferred['id']}/confirm",
                    {"revision": preferred["revision"]},
                )
                routine_body = {
                    "confirmed": True,
                    "target_date": str(future),
                    "horizon_days": 1,
                    "daily_windows": [
                        {"title": "明确午休", "start": "12:00", "end": "12:30"}
                    ],
                }
                before_routine = json.load(opener.open(origin + "/api/data-export"))[
                    "resources"
                ]
                routine = write_json("/daily-routine-preview", routine_body)
                assert routine["candidates"][0]["can_add"]
                assert (
                    json.load(opener.open(origin + "/api/data-export"))["resources"]
                    == before_routine
                )
                args = {
                    "candidate_id": routine["candidates"][0]["id"],
                    "expected_source_revision": routine["source_revision"],
                    "request": routine_body,
                }
                write_json("/daily-routine-dismiss", args)
                assert write_json("/daily-routine-preview", routine_body)["candidates"][
                    0
                ]["dismissed"]
                routine_body["daily_windows"][0]["title"] = "明确休息"
                routine = write_json("/daily-routine-preview", routine_body)
                args.update(
                    candidate_id=routine["candidates"][0]["id"], request=routine_body
                )
                routine_draft = write_json("/daily-routine-drafts", args)
                write_json(
                    f"/drafts/{routine_draft['id']}/confirm",
                    {"revision": routine_draft["revision"]},
                )
                assert len(json.load(opener.open(origin + "/api/fixed-events"))) >= 1
                writer = PdfWriter()
                writer.add_blank_page(width=500, height=700)
                pdf = BytesIO()
                writer.write(pdf)
                boundary = "test-" + uuid4().hex
                multipart = (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
                    + pdf.getvalue()
                    + f"\r\n--{boundary}--\r\n".encode()
                )
                # Verify the unified conflict service is actually bundled, using
                # explicit campus facts and a user-confirmed directional matrix.
                settings = json.load(opener.open(origin + "/api/settings"))
                settings["data"]["campus_transfers"] = [
                    {"from_campus": "五山", "to_campus": "大学城", "minutes": 40}
                ]
                write_json("/settings", settings, "PUT")
                existing = json.load(opener.open(origin + "/api/courses"))[0]["data"]
                existing["campus"] = "五山"
                campus_draft = write_json(
                    "/drafts/timetable",
                    {"semester_label": "synthetic campuses", "courses": [existing]},
                )
                write_json(
                    f"/drafts/{campus_draft['id']}/confirm",
                    {"revision": campus_draft["revision"]},
                )
                transfer_draft = write_json(
                    "/drafts/timetable",
                    {
                        "semester_label": "synthetic transfer",
                        "courses": [
                            {
                                "source_key": "frozen-transfer",
                                "name": "冻结包跨校区课",
                                "campus": "大学城",
                                "weekday": local_day.isoweekday(),
                                "weeks": [1],
                                "periods": [2],
                            }
                        ],
                    },
                )
                conflict_review = write_json(
                    f"/drafts/{transfer_draft['id']}/conflict-preview",
                    {
                        "revision": transfer_draft["revision"],
                        "payload": transfer_draft["data"]["payload"],
                    },
                )
                shortfall = next(
                    i
                    for i in conflict_review["issues"]
                    if i["code"] == "transfer_shortfall"
                )
                assert (
                    shortfall["required_minutes"],
                    shortfall["available_minutes"],
                    shortfall["shortfall_minutes"],
                ) == (40, 20, 20)
                assert len(json.load(opener.open(origin + "/api/courses"))) == 1
                transfer_saved = write_json(
                    f"/drafts/{transfer_draft['id']}/confirm",
                    {
                        "revision": transfer_draft["revision"],
                        "conflict_token": conflict_review["conflict_token"],
                    },
                )
                assert transfer_saved["conflict_reviewed"] is True
                assert (
                    json.load(opener.open(origin + agenda_query))["conflict_report"][
                        "conflict_count"
                    ]
                    >= 1
                )

                asset = json.load(
                    request(
                        "/timetable-assets",
                        multipart,
                        "multipart/form-data; boundary=" + boundary,
                    )
                )
                assert asset["data"]["pages"][0]["type"] == "scanned_pdf"
                image = opener.open(
                    origin + f"/api/assets/{asset['id']}/pages/1"
                ).read()
                assert image.startswith(b"\x89PNG")
                exported = json.load(opener.open(origin + "/api/data-export"))
                assert len(exported["asset_files_base64"]) == 2
                assert (
                    request(
                        "/data-delete",
                        json.dumps({"confirmation": "删除我的所有数据"}).encode(),
                    ).status
                    == 200
                )
                assert list((root / "data/uploads").iterdir()) == []
                return {
                    "passed": True,
                    "scope": "actual frozen backend, temporary local profile, no model calls",
                    "checks": [
                        "isolated database identity",
                        "frozen today planner creates review-only one-day draft",
                        "frozen course move, cancel, restore and audit history",
                        "frozen nonconsecutive course intervals and stable segment IDs",
                        "frozen planner uses the nonteaching gap and confirms one block",
                        "frozen unified conflict preview is read-only, checks directional transfer shortfall and saves a reviewed receipt",
                        "frozen weekly protection preview identifies existing plans and blocks next-week scheduling without silently changing saved blocks",
                        "frozen capacity endpoint matches planner windows, reports blocked work and preserves all resources without superseding a pending draft",
                        "frozen repair preview is read-only, repeated requests reuse one draft, confirmation removes only an invalid old suggestion and retains a snapshot",
                        "frozen soft preferences, read-only comparison and risk reports, selected plan confirmation",
                        "frozen explicit routine preview, durable dismissal and reviewed event save",
                        "PDFium dynamic library loads",
                        "PDF upload and render",
                        "page PNG served",
                        "original and page export",
                        "asset cleanup",
                    ],
                }
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.service.resolve())
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
