"""Synthetic confirmed calendar changes; no person B execution service."""

from copy import deepcopy
from datetime import datetime

import pytest

from app import planner
from app.planner import build_plan, instant
from tests.test_foundation import make_client, register_login
from tests.test_planner import fixture
from tests.test_scheduling_constraints import confirm, resources, seed_work, write
from tests.test_today_plan import block


def repair_input():
    p = fixture()
    p.update(
        repair=True, occurrences=[], fixed_events=[], constraints=[], horizon_days=7
    )
    p["tasks"][0]["data"]["due_at"] = None
    p["steps"] = p["steps"][:1]
    p["steps"][0]["data"]["estimated_minutes"] = 120
    p["preserved_blocks"] = [
        block("first", start="12:00", end="13:00"),
        block("second", start="14:00", end="15:00"),
    ]
    p["current_blocks"] = deepcopy(p["preserved_blocks"])
    return p


def test_valid_old_slots_are_retained_exactly_without_earlier_repacking():
    p = repair_input()
    before = deepcopy(p)
    r = build_plan(p)
    assert r["blocks"] == p["current_blocks"]
    assert not r["changes"]["added_ids"] and not r["removed_blocks"]
    assert p == before and r == build_plan(p)


@pytest.mark.parametrize("cause", ["fixed", "course", "protected"])
def test_only_conflicting_slot_moves_and_time_is_not_reported_as_actual(cause):
    p = repair_input()
    event = {
        "starts_at": "2026-10-14T12:00:00+08:00",
        "ends_at": "2026-10-14T13:00:00+08:00",
        "title": "合成变化",
    }
    if cause == "fixed":
        p["fixed_events"] = [event]
    elif cause == "course":
        p["occurrences"] = [event]
    else:
        p["constraints"] = [
            {
                "id": "c",
                "revision": 1,
                "data": {
                    **event,
                    "timezone": "Asia/Shanghai",
                    "active": True,
                    "confirmed": True,
                },
            }
        ]
    r = build_plan(p)
    assert {b["id"] for b in r["removed_blocks"]} == {"first"}
    assert r["changes"]["retained_ids"] == ["second"]
    assert next(b for b in r["blocks"] if b["id"] == "second") == p["current_blocks"][1]
    assert r["capacity"]["proposed_minutes"] == 60
    assert p["steps"][0]["data"]["spent_minutes"] == 0
    assert not r["unscheduled"]
    assert all(
        instant(b["ends_at"]) <= instant(event["starts_at"])
        or instant(b["starts_at"]) >= instant(event["ends_at"])
        for b in r["blocks"]
    )


@pytest.mark.parametrize(
    "protected_kind", ["locked", "completed", "ongoing", "outside"]
)
def test_immutable_facts_are_not_removed(protected_kind):
    p = repair_input()
    b = p["preserved_blocks"][0]
    if protected_kind == "locked":
        b["locked"] = True
    elif protected_kind == "completed":
        b["status"] = "completed"
    elif protected_kind == "ongoing":
        p["now_utc"] = instant("2026-10-14T12:30:00+08:00")
    else:
        p["horizon_days"] = 1
        b.update(
            starts_at="2026-10-15T12:00:00+08:00", ends_at="2026-10-15T13:00:00+08:00"
        )
    p["fixed_events"] = [{"starts_at": b["starts_at"], "ends_at": b["ends_at"]}]
    p["current_blocks"] = deepcopy(p["preserved_blocks"])
    r = build_plan(p)
    assert b in r["blocks"]
    assert b["id"] not in r["changes"]["removed_ids"]
    if protected_kind != "completed":
        assert r["warnings"]


def test_dependency_changes_cascade_instead_of_leaving_invalid_child():
    p = repair_input()
    second = deepcopy(p["steps"][0])
    second["id"] = "b"
    second["data"].update(estimated_minutes=60, dependency_ids=["a"])
    p["steps"][0]["data"]["estimated_minutes"] = 60
    p["steps"].append(second)
    p["preserved_blocks"][1]["step_id"] = "b"
    p["current_blocks"] = deepcopy(p["preserved_blocks"])
    p["fixed_events"] = [
        {
            "starts_at": "2026-10-14T09:00:00+08:00",
            "ends_at": "2026-10-14T14:00:00+08:00",
        }
    ]
    r = build_plan(p)
    assert set(r["changes"]["removed_ids"]) == {"first", "second"}
    a_end = max(instant(b["ends_at"]) for b in r["blocks"] if b["step_id"] == "a")
    assert (
        min(instant(b["starts_at"]) for b in r["blocks"] if b["step_id"] == "b")
        >= a_end
    )


def test_capacity_shortage_removes_invalid_suggestion_without_inventing_future_work():
    p = repair_input()
    p["horizon_days"] = 1
    p["fixed_events"] = [
        {
            "starts_at": "2026-10-14T09:00:00+08:00",
            "ends_at": "2026-10-14T18:00:00+08:00",
        }
    ]
    r = build_plan(p)
    assert not r["blocks"] and len(r["removed_blocks"]) == 2
    assert r["capacity"]["unallocated_minutes"] == 120


@pytest.mark.asyncio
async def test_readonly_dedup_confirm_preserve_identity_restart_and_no_loop(
    tmp_path, monkeypatch
):
    clock = datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    monkeypatch.setattr(planner, "now", lambda: clock)
    c = make_client(tmp_path)
    with c:
        h = register_login(c)
        seed_work(c, h)
        first = write(c, h, "/plan-drafts", {"horizon_days": 7}).json()
        assert confirm(c, h, first).status_code == 200
        old = c.get("/api/plan-blocks").json()
        before = c.get("/api/data-export").json()["resources"]
        assert c.get("/api/replanning").json()["needs_changes"] is False
        assert c.get("/api/data-export").json()["resources"] == before
        assert write(c, h, "/replan-drafts", {}).status_code == 409
        target = old[0]
        fixed = write(
            c,
            h,
            "/fixed-events",
            {
                "title": "合成临时事项",
                "starts_at": target["data"]["starts_at"],
                "ends_at": target["data"]["ends_at"],
            },
        )
        assert fixed.status_code == 200, fixed.text
        before = c.get("/api/data-export").json()["resources"]
        report = c.get("/api/replanning").json()
        assert (
            report["needs_changes"]
            and report["execution_integration"] == "authoritative_execution_v1"
        )
        assert target["id"] in {b["id"] for b in report["removed"]}
        assert c.get("/api/data-export").json()["resources"] == before
        response = write(c, h, "/replan-drafts", {})
        assert response.status_code == 200, response.text
        draft = response.json()
        assert write(c, h, "/replan-drafts", {}).json()["id"] == draft["id"]
        assert (
            len(
                [
                    d
                    for d in c.get("/api/drafts").json()
                    if d["data"]["draft_kind"] == "plan"
                ]
            )
            == 1
        )
        assert c.get("/api/plan-blocks").json() == old
        result = confirm(c, h, draft)
        assert result.status_code == 200, result.text
        assert confirm(c, h, draft).json() == result.json()
        new = {b["id"]: b for b in c.get("/api/plan-blocks").json()}
        for b in old:
            if b["id"] in report["retained_ids"]:
                assert new[b["id"]] == b
        assert not c.get("/api/replanning").json()["needs_changes"]
        assert (
            resources(c, "plan_snapshot")[-1]["data"]["approved_plan"]["replanning"][
                "rule_version"
            ]
            == "preserve-valid-1"
        )
        assert all(s["data"]["spent_minutes"] == 0 for s in resources(c, "step"))
    c2 = make_client(tmp_path)
    with c2:
        c2.cookies.update(c.cookies)
        # Login explicitly after process recreation using the same persisted database.
        csrf = c2.get("/api/csrf").json()["csrf_token"]
        assert (
            c2.post(
                "/api/auth/login",
                data={
                    "username": "alice@example.com",
                    "password": "Student!Password2026",
                },
                headers={"X-CSRF-Token": csrf, "Origin": "http://testserver"},
            ).status_code
            == 204
        )
        assert not c2.get("/api/replanning").json()["needs_changes"]


@pytest.mark.asyncio
async def test_stale_owner_and_elapsed_guards(tmp_path, monkeypatch):
    clock = datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    monkeypatch.setattr(planner, "now", lambda: clock)
    c = make_client(tmp_path)
    with c:
        h = register_login(c)
        seed_work(c, h)
        draft = write(c, h, "/replan-drafts", {}).json()
        assert c.get("/api/plan-blocks").json() == []
        write(
            c,
            h,
            "/fixed-events",
            {
                "title": "新事项",
                "starts_at": "2026-10-14T17:00:00+08:00",
                "ends_at": "2026-10-14T18:00:00+08:00",
            },
        )
        assert confirm(c, h, draft).status_code == 409
        fresh = write(c, h, "/replan-drafts", {}).json()
        clock = instant(fresh["data"]["payload"]["blocks"][0]["starts_at"])
        from datetime import timedelta

        clock += timedelta(seconds=1)
        assert confirm(c, h, fresh).status_code == 409
        assert c.get("/api/plan-blocks").json() == []
        c.cookies.clear()
        assert c.get("/api/replanning").status_code == 401
        assert c.get("/api/replanning?horizon_days=8").status_code in (401, 422)


def test_removed_slot_starting_during_review_is_not_deleted(tmp_path, monkeypatch):
    clock = instant("2026-10-14T08:00:00+08:00")
    monkeypatch.setattr(planner, "now", lambda: clock)
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        original = write(c, h, "/plan-drafts", {}).json()
        assert confirm(c, h, original).status_code == 200
        old = c.get("/api/plan-blocks").json()
        target = min(old, key=lambda b: instant(b["data"]["starts_at"]))
        write(
            c,
            h,
            "/fixed-events",
            {
                "title": "临时事项",
                "starts_at": target["data"]["starts_at"],
                "ends_at": target["data"]["ends_at"],
            },
        )
        draft = write(c, h, "/replan-drafts", {}).json()
        clock = instant(target["data"]["starts_at"])
        from datetime import timedelta

        clock += timedelta(seconds=1)
        snapshots = resources(c, "plan_snapshot")
        assert confirm(c, h, draft).status_code == 409
        assert c.get("/api/plan-blocks").json() == old
        assert resources(c, "plan_snapshot") == snapshots
        c.cookies.clear()
        other = register_login(c, "other@example.com")
        assert c.get("/api/replanning").json()["retained_ids"] == []
        assert confirm(c, other, draft).status_code == 404
