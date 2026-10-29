"""Capacity reports use real planner facts without saving or superseding plans."""

from copy import deepcopy
from datetime import datetime

import pytest

from app import planner
from app.planner import build_plan
from tests.test_foundation import make_client, register_login
from tests.test_planner import fixture
from tests.test_scheduling_constraints import confirm, protected, seed_work, write
from tests.test_today_plan import block


def test_capacity_uses_union_of_busy_time_buffer_remaining_day_and_budget():
    p = fixture()
    p["now_utc"] = datetime.fromisoformat("2026-10-14T10:30:31+08:00")
    p["settings"]["daily_limit_minutes"] = 600
    p["fixed_events"] = [
        {
            "starts_at": "2026-10-14T10:50:00+08:00",
            "ends_at": "2026-10-14T12:00:00+08:00",
        }
    ]
    p["constraints"] = [
        protected(
            starts_at="2026-10-14T11:30:00+08:00", ends_at="2026-10-14T13:00:00+08:00"
        )
    ]
    before = deepcopy(p)
    result = build_plan(p)
    r = result["capacity"]
    assert p == before and result == build_plan(p)
    assert (
        r["days"][0]["free_minutes"] == 300
    )  # Union ends at 13:00, not double-counted.
    assert r["capacity_upper_bound_minutes"] == 300
    assert r["required_minutes"] == r["proposed_minutes"] == 180
    assert r["unallocated_minutes"] == 0
    assert r["days"][0]["free_windows"][0]["starts_at"] == "2026-10-14T05:00:00Z"
    assert r["days"][0]["budget_remaining_minutes"] == 600


def test_time_upper_bound_does_not_promise_deadline_or_dependency_feasibility():
    p = fixture()
    p["tasks"][0]["data"]["due_at"] = "2026-10-14T12:00:00+08:00"
    r = build_plan(p)["capacity"]
    assert r["capacity_upper_bound_minutes"] == 180
    assert r["required_minutes"] == 180
    assert r["proposed_minutes"] == 50
    assert r["unallocated_minutes"] == 130
    assert len(r["unscheduled"]) == 2
    assert r["days"][0]["proposed_minutes"] == 50


def test_fragmented_capacity_is_an_upper_bound_not_false_scheduled_work():
    p = fixture()
    p.update(occurrences=[], steps=p["steps"][:1])
    p["settings"]["study_windows"] = [
        {"start": "11:00", "end": "11:10"},
        {"start": "12:00", "end": "12:10"},
    ]
    r = build_plan(p)["capacity"]
    assert r["capacity_upper_bound_minutes"] == 20
    assert r["proposed_minutes"] == 0
    assert r["unallocated_minutes"] == r["required_minutes"] == 120


def test_missing_estimates_are_unknown_and_empty_work_never_invents_tasks():
    p = fixture()
    p["steps"] = []
    r = build_plan(p)["capacity"]
    assert r["unknown_estimate_count"] == 1
    assert r["unscheduled"][0]["remaining_minutes"] is None
    assert r["required_minutes"] == r["proposed_minutes"] == 0
    p["tasks"] = []
    r = build_plan(p)["capacity"]
    assert r["capacity_upper_bound_minutes"] == 180
    assert r["unknown_estimate_count"] == 0 and not r["unscheduled"]


def test_locked_reservation_reduces_budget_and_work_without_claiming_actual_effort():
    p = fixture()
    p["preserved_blocks"] = [{**block("lock"), "locked": True}]
    p["current_blocks"] = deepcopy(p["preserved_blocks"])
    r = build_plan(p)["capacity"]
    assert r["reserved_work_minutes"] == 60
    assert r["required_minutes"] == 120
    assert r["days"][0]["budget_remaining_minutes"] == 120
    assert r["capacity_upper_bound_minutes"] == r["proposed_minutes"] == 120
    # The 60 minutes left in step a use a 50-minute gap and a 10-minute tail,
    # followed by step b; the locked hour keeps its original identity.
    assert r["changes"] == {"added": 3, "retained": 1, "removed": 0}
    assert p["steps"][0]["data"]["spent_minutes"] == 0


def test_invalid_locked_fact_remains_visible_and_does_not_count_as_work():
    p = fixture()
    p["steps"] = p["steps"][:1]
    p["preserved_blocks"] = [
        {**block("conflicting", start="10:30", end="11:30"), "locked": True}
    ]
    r = build_plan(p)["capacity"]
    assert r["warnings"]
    assert r["reserved_work_minutes"] == r["proposed_minutes"] == 0
    assert r["required_minutes"] == r["unallocated_minutes"] == 120
    assert "解锁" in r["unscheduled"][0]["reason"]


def test_future_reservation_is_not_duplicated_in_today_demand():
    p = fixture()
    p["scope"] = "today"
    p["tasks"][0]["data"]["due_at"] = None
    p["steps"] = p["steps"][:1]
    p["steps"][0]["data"]["estimated_minutes"] = 60
    p["preserved_blocks"] = [block("tomorrow", day=15)]
    r = build_plan(p)["capacity"]
    assert r["reserved_work_minutes"] == 60
    assert r["required_minutes"] == r["proposed_minutes"] == 0
    assert r["days"][0]["capacity_upper_bound_minutes"] == 180


def test_dst_capacity_counts_elapsed_minutes_and_local_day():
    p = fixture()
    p.update(
        target_date="2026-03-08",
        now_utc=datetime.fromisoformat("2026-03-08T05:00:00Z"),
        occurrences=[],
    )
    p["settings"].update(
        timezone="America/New_York", study_windows=[{"start": "01:00", "end": "04:00"}]
    )
    p["tasks"][0]["data"]["due_at"] = None
    r = build_plan(p)["capacity"]
    assert r["days"][0]["date"] == "2026-03-08"
    assert r["capacity_upper_bound_minutes"] == 120
    assert r["proposed_minutes"] == 120 and r["unallocated_minutes"] == 60


def test_report_consumes_recorded_minutes_without_replacing_them_by_planned_time():
    p = fixture()
    p["steps"] = p["steps"][:1]
    p["steps"][0]["data"].update(estimated_minutes=60, spent_minutes=25)
    r = build_plan(p)["capacity"]
    assert r["required_minutes"] == r["proposed_minutes"] == 35
    assert p["steps"][0]["data"]["spent_minutes"] == 25


def test_later_week_protection_changes_capacity_without_materializing_infinite_events():
    p = fixture()
    p.update(
        target_date="2026-10-21",
        now_utc=datetime.fromisoformat("2026-10-21T08:00:00+08:00"),
        occurrences=[],
    )
    p["tasks"][0]["data"]["due_at"] = None
    p["constraints"] = [
        protected(
            recurrence="weekly",
            weekdays=[3],
            valid_until=None,
            starts_at="2026-10-14T09:00:00+08:00",
            ends_at="2026-10-14T18:00:00+08:00",
        )
    ]
    r = build_plan(p)["capacity"]
    assert r["capacity_upper_bound_minutes"] == 0
    assert r["days"][0]["free_windows"] == []
    assert r["unallocated_minutes"] == 180
    p["constraints"][0]["data"]["active"] = False
    assert build_plan(p)["capacity"]["capacity_upper_bound_minutes"] == 180


def test_readonly_capacity_matches_draft_preserves_pending_and_survives_restart(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-13T23:30:00Z")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        draft = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        before = c.get("/api/data-export").json()["resources"]
        report = c.get("/api/planning-capacity?scope=today")
        assert report.status_code == 200, report.text
        r = report.json()
        assert r == draft["data"]["payload"]["capacity"]
        assert r["target_date"] == "2026-10-14" and r["horizon_days"] == 1
        assert c.get("/api/data-export").json()["resources"] == before
        assert c.get("/api/planning-capacity?scope=today").json() == r
        assert confirm(c, h, draft).status_code == 200
        # No new drafts or snapshots are written by a capacity read.
        before = c.get("/api/data-export").json()["resources"]
        after_save = c.get("/api/planning-capacity?scope=today").json()
        assert after_save["changes"]["retained"] > 0
        assert c.get("/api/data-export").json()["resources"] == before
        cookie = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert c.get("/api/planning-capacity?scope=today").json() == after_save


@pytest.mark.parametrize(
    "query",
    [
        "horizon_days=0",
        "horizon_days=8",
        "scope=no",
        "scope=today&horizon_days=7",
        "scope=today&target_date=2026-10-14",
        "target_date=2026-10-13",
    ],
)
def test_bad_capacity_ranges_rejected(tmp_path, monkeypatch, query):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        register_login(c)
        assert c.get("/api/planning-capacity?" + query).status_code == 422


def test_capacity_auth_owner_isolation_and_changed_fact_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        assert c.get("/api/planning-capacity").status_code == 401
        h = register_login(c)
        seed_work(c, h)
        before = c.get("/api/planning-capacity?scope=today").json()
        assert before["required_minutes"] == 360
        s = c.get("/api/settings").json()
        s["data"]["daily_limit_minutes"] = 90
        assert write(c, h, "/settings", s, "PUT").status_code == 200
        after = c.get("/api/planning-capacity?scope=today").json()
        assert after["source_revision"] > before["source_revision"]
        assert after["capacity_upper_bound_minutes"] == 90
        assert c.post("/api/auth/logout", headers=h).status_code == 204
        register_login(c, "bob@example.com")
        other = c.get("/api/planning-capacity?scope=today").json()
        assert other["required_minutes"] == 0 and not other["unscheduled"]
