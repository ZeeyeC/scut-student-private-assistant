"""Weekly hard protection: bounded facts, persistence and planner integration."""

from copy import deepcopy
from datetime import datetime

import pytest

from app import planner
from app.constraints import expand_constraints
from app.contracts import SchedulingConstraint
from tests.test_foundation import make_client, register_login
from tests.test_planner import fixture
from tests.test_scheduling_constraints import (
    confirm,
    protected,
    resources,
    seed_work,
    spec,
    write,
)


def at(s):
    return datetime.fromisoformat(s)


def weekly(**changes):
    return protected(
        recurrence="weekly", weekdays=[3, 5], valid_until="2026-10-28", **changes
    )


def test_weekly_selected_days_inclusive_end_stable_identity_and_disable():
    row = weekly()
    original = deepcopy(row)
    lower, upper = at("2026-10-14T00:00:00+08:00"), at("2026-11-01T00:00:00+08:00")
    result = expand_constraints([row], lower, upper)
    assert [r["occurrence_date"] for r in result] == [
        "2026-10-14",
        "2026-10-16",
        "2026-10-21",
        "2026-10-23",
        "2026-10-28",
    ]
    assert result[0]["id"] == "protected:2026-10-14"
    assert all(r["constraint_id"] == "protected" and r["revision"] == 1 for r in result)
    assert row == original and result == expand_constraints([row], lower, upper)
    row["data"]["active"] = False
    assert expand_constraints([row], lower, upper) == []


def test_sunday_overnight_tail_is_protected_after_series_end_and_never_on_free_days():
    row = weekly(
        starts_at="2026-10-18T22:00:00+08:00", ends_at="2026-10-19T02:00:00+08:00"
    )
    row["data"].update(weekdays=[7], valid_until="2026-10-18")
    result = expand_constraints(
        [row], at("2026-10-19T00:00:00+08:00"), at("2026-10-20T00:00:00+08:00")
    )
    assert len(result) == 1 and result[0]["occurrence_date"] == "2026-10-18"
    assert not expand_constraints(
        [row], at("2026-10-19T02:00:00+08:00"), at("2026-10-26T00:00:00+08:00")
    )


def test_weekly_keeps_wall_clock_across_offset_change():
    row = weekly(
        timezone="America/New_York",
        starts_at="2026-10-30T09:00:00-04:00",
        ends_at="2026-10-30T10:00:00-04:00",
    )
    row["data"].update(weekdays=[5], valid_until="2026-11-13")
    windows = expand_constraints(
        [row], at("2026-10-30T00:00:00-04:00"), at("2026-11-14T00:00:00-05:00")
    )
    assert [r["data"]["starts_at"] for r in windows] == [
        "2026-10-30T09:00:00-04:00",
        "2026-11-06T09:00:00-05:00",
        "2026-11-13T09:00:00-05:00",
    ]


@pytest.mark.parametrize(
    "starts,ends,day",
    [
        ("2026-03-01T02:30:00-05:00", "2026-03-01T03:30:00-05:00", "2026-03-08"),
        ("2026-10-25T01:30:00-04:00", "2026-10-25T02:30:00-04:00", "2026-11-01"),
    ],
)
def test_ambiguous_or_nonexistent_local_time_is_not_guessed(starts, ends, day):
    row = weekly(timezone="America/New_York", starts_at=starts, ends_at=ends)
    row["data"].update(weekdays=[7], valid_until=None)
    with pytest.raises(ValueError, match="夏令时"):
        expand_constraints(
            [row], at(day + "T00:00:00-05:00"), at(day + "T23:59:00-05:00")
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"weekdays": []},
        {"weekdays": [8]},
        {"valid_until": "2026-10-13"},
        {"ends_at": "2026-10-15T18:00:00+08:00"},
    ],
)
def test_invalid_weekly_rule_rejected(patch):
    with pytest.raises(ValueError):
        SchedulingConstraint.model_validate(
            {**spec(recurrence="weekly", weekdays=[3]), **patch}
        )


def test_repeated_constraints_apply_to_later_week_and_locked_block_without_moving_facts():
    p = fixture()
    p.update(
        now_utc=at("2026-10-21T10:30:00+08:00"),
        target_date="2026-10-21",
        occurrences=[],
        constraints=[weekly()],
    )
    p["tasks"][0]["data"]["due_at"] = "2026-10-21T18:00:00+08:00"
    p["preserved_blocks"] = [
        {
            "id": "locked",
            "task_id": "t1",
            "step_id": "a",
            "title": "锁定练习",
            "starts_at": "2026-10-21T14:00:00+08:00",
            "ends_at": "2026-10-21T15:00:00+08:00",
            "status": "suggested",
            "locked": True,
        }
    ]
    before = deepcopy(p)
    result = planner.build_plan(p)
    assert p == before
    assert result["blocks"][0] == p["preserved_blocks"][0]
    assert any("禁排" in w for w in result["warnings"])
    assert result["protected_windows"][0]["occurrence_date"] == "2026-10-21"
    p["preserved_blocks"] = []
    result = planner.build_plan(p)
    assert result["blocks"] and result["blocks"][0]["explanation"][
        "constraint_revisions"
    ] == {"protected": 1}
    assert all(
        at(b["ends_at"]) <= at("2026-10-21T14:00:00+08:00")
        or at(b["starts_at"]) >= at("2026-10-21T17:00:00+08:00")
        for b in result["blocks"]
    )


def test_weekly_preview_confirm_restart_disable_and_stale_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(planner, "now", lambda: at("2026-10-14T08:00:00+08:00"))
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        old = write(c, h, "/plan-drafts", {"horizon_days": 7}).json()
        payload = {
            "constraint": spec(
                recurrence="weekly", weekdays=[3, 5], valid_until="2026-10-30"
            )
        }
        draft = write(c, h, "/drafts/scheduling-constraint", payload).json()
        preview = write(
            c,
            h,
            f"/drafts/{draft['id']}/constraint-preview?start=2026-10-14&end=2026-10-30",
            {"revision": draft["revision"], "payload": draft["data"]["payload"]},
        )
        assert preview.status_code == 200, preview.text
        assert len(preview.json()["windows"]) == 6
        assert c.get("/api/scheduling-constraints").json() == []
        saved = confirm(c, h, draft, key="weekly-save")
        assert (
            saved.status_code == 200
            and confirm(c, h, draft, key="weekly-save").json() == saved.json()
        )
        assert confirm(c, h, old).status_code == 409
        row = c.get("/api/scheduling-constraints").json()[0]
        agenda = c.get("/api/calendar-events?start=2026-10-21&end=2026-10-21").json()
        windows = [e for e in agenda["events"] if e["kind"] == "scheduling_constraint"]
        assert len(windows) == 1 and windows[0]["constraint_id"] == row["id"]
        plan = write(
            c, h, "/plan-drafts", {"target_date": "2026-10-21", "horizon_days": 1}
        ).json()
        assert (
            plan["data"]["payload"]["protected_windows"][0]["constraint_id"]
            == row["id"]
        )
        assert (
            write(
                c,
                h,
                f"/scheduling-constraints/{row['id']}",
                {"revision": row["revision"], "active": False},
                "PATCH",
            ).status_code
            == 200
        )
        assert confirm(c, h, plan).status_code == 409
        assert not c.get("/api/calendar-events?start=2026-10-21&end=2026-10-21").json()[
            "events"
        ]
        cookie = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        rows = c.get("/api/scheduling-constraints").json()
        assert len(rows) == 1 and rows[0]["data"]["active"] is False
        assert len(resources(c, "planning_event")) == 2


def test_weekly_amendment_changes_one_resource_and_version_guard_is_shared(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = write(
            c,
            h,
            "/drafts/scheduling-constraint",
            {"constraint": spec(recurrence="weekly", weekdays=[3])},
        ).json()
        assert confirm(c, h, d).status_code == 200
        row = c.get("/api/scheduling-constraints").json()[0]
        amendment = {
            "constraint": spec(
                recurrence="weekly", weekdays=[5], valid_until="2026-10-30"
            ),
            "constraint_id": row["id"],
            "constraint_revision": row["revision"],
        }
        edit = write(c, h, "/drafts/scheduling-constraint", amendment).json()
        assert confirm(c, h, edit).status_code == 200
        rows = c.get("/api/scheduling-constraints").json()
        assert (
            len(rows) == 1 and rows[0]["id"] == row["id"] and rows[0]["revision"] == 2
        )
        assert rows[0]["data"]["weekdays"] == [5]
        response = write(
            c,
            h,
            f"/drafts/{d['id']}/constraint-preview?start=2026-10-14&end=2026-10-30",
            {"revision": 1, "payload": d["data"]["payload"]},
        )
        assert response.status_code == 409


def test_ambiguous_weekly_anchor_with_explicit_later_offset_cannot_choose_later_future_folds():
    row = weekly(
        timezone="America/New_York",
        starts_at="2026-11-01T01:30:00-05:00",
        ends_at="2026-11-01T02:30:00-05:00",
    )
    row["data"].update(weekdays=[7], valid_until=None)
    with pytest.raises(ValueError, match="夏令时"):
        expand_constraints(
            [row], at("2026-11-01T00:00:00-04:00"), at("2026-11-02T00:00:00-05:00")
        )
