"""Real A+B routes with isolated SQLite; readiness probes, no model calls."""

from datetime import datetime

import pytest

from app import planner
from tests.test_execution import (
    correction,
    execution_body,
    save,
    seed_execution,
    summary,
)
from tests.test_execution_timers import command, start
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import confirm, draft, resources, write


@pytest.fixture(autouse=True)
def fixed_planning_clock(monkeypatch):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )


def get(c, path):
    response = c.get("/api" + path)
    assert response.status_code == 200, response.text
    return response.json()


def post(c, h, path, body, method="POST"):
    response = write(c, h, path, body, method)
    assert response.status_code == 200, response.text
    return response.json()


def plan(c, h, repair=False):
    return post(
        c,
        h,
        "/replan-drafts" if repair else "/plan-drafts",
        {
            "target_date": "2026-10-14",
            "horizon_days": 7,
        },
    )


def goal(c, h, task_id=None):
    return post(
        c,
        h,
        "/goals",
        {
            "title": "合成联合目标",
            "weekly_budget_minutes": 600,
            "priority": 3,
            "load_category": "study",
            "allowed_adjustment": "reduce",
            "subtasks": (
                [
                    {
                        "title": "合成练习",
                        "status": "open",
                        "estimated_minutes": 60,
                        "task_id": task_id,
                    }
                ]
                if task_id
                else []
            ),
        },
    )


def profile(c, h):
    return post(
        c,
        h,
        "/profile",
        {
            "revision": get(c, "/profile")["revision"],
            "data": {
                "timezone": "Asia/Shanghai",
                "preferences": {
                    "focus_minutes": 45,
                    "preferred_study_windows": [
                        {
                            "weekdays": [3],
                            "start": "16:00",
                            "end": "17:00",
                            "task_type": "deep",
                        }
                    ],
                },
            },
        },
        "PUT",
    )


def test_actual25_and_correction20_feed_real_capacity_and_replanning(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        record = save(c, h, execution_body(c, ids))
        capacity = get(c, "/planning-capacity?target_date=2026-10-14&horizon_days=7")
        assert capacity["required_minutes"] == 35
        assert capacity["proposed_minutes"] == 35
        old = plan(c, h, repair=True)
        assert old["data"]["payload"]["capacity"]["required_minutes"] == 35
        post(c, h, f"/executions/{record['id']}/corrections", correction(c, ids))
        assert confirm(c, h, old).status_code == 409
        capacity = get(c, "/planning-capacity?target_date=2026-10-14&horizon_days=7")
        assert capacity["required_minutes"] == 40
        assert summary(c, ids)["actual_minutes"] == 20
        assert get(c, f"/tasks/{ids['task']}")["data"]["status"] == "open"


@pytest.mark.parametrize("change", ["execution", "profile", "goal"])
def test_b_writes_invalidate_a_draft_and_option_selection_without_plan_write(
    tmp_path, change
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        options = get(c, "/planning-options?target_date=2026-10-14&horizon_days=7")
        old = plan(c, h)
        if change == "execution":
            save(c, h, execution_body(c, ids))
        elif change == "profile":
            profile(c, h)
        else:
            goal(c, h, ids["task"])
        before = get(c, "/plan-blocks")
        assert confirm(c, h, old).status_code == 409
        selected = write(
            c,
            h,
            "/plan-drafts",
            {
                "target_date": "2026-10-14",
                "horizon_days": 7,
                "strategy": "preferred",
                "expected_source_revision": options["source_revision"],
            },
        )
        assert selected.status_code == 409
        assert get(c, "/plan-blocks") == before


def test_a_selective_replan_cannot_remove_a_b_timer_target(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        timer = start(c, h, ids)
        protection = draft(
            c,
            h,
            starts_at="2026-10-14T10:00:00+08:00",
            ends_at="2026-10-14T11:00:00+08:00",
        )
        assert confirm(c, h, protection).status_code == 200
        report = get(c, "/replanning?target_date=2026-10-14&horizon_days=7")
        assert ids["block"] in report["retained_ids"]
        assert ids["block"] not in [r["id"] for r in report["removed"]]
        assert report["warnings"]
        assert (
            write(
                c, h, "/replan-drafts", {"target_date": "2026-10-14", "horizon_days": 7}
            ).status_code
            == 409
        )
        assert resources(c, "plan_snapshot") == []
        assert any(b["id"] == ids["block"] for b in get(c, "/plan-blocks"))
        command(c, h, timer, "discard")
        assert confirm(c, h, plan(c, h, repair=True)).status_code == 200


def test_a_snapshots_and_b_corrections_remain_separate_in_weekly_review(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        assert confirm(c, h, plan(c, h)).status_code == 200
        ids["block"] = get(c, "/plan-blocks")[0]["id"]
        record = save(c, h, execution_body(c, ids))
        assert confirm(c, h, plan(c, h, repair=True)).status_code == 200
        report = get(c, "/weekly-review?week_start=2026-10-12&timezone=Asia%2FShanghai")
        assert report["plans"]["original"]["known_minutes"] == 60
        assert report["plans"]["adjusted"]["known_minutes"] == 95
        assert report["execution"]["observed_seconds"] == 1500
        assert report["execution"]["actual_seconds"] is None
        assert len(report["execution"]["missing_plan_block_ids"]) == 1
        assert len(resources(c, "plan_snapshot")) == 2
        post(c, h, f"/executions/{record['id']}/corrections", correction(c, ids))
        corrected = get(
            c, "/weekly-review?week_start=2026-10-12&timezone=Asia%2FShanghai"
        )
        assert corrected["execution"]["observed_seconds"] == 1200
        assert corrected["execution"]["actual_seconds"] is None
        assert corrected["plans"] == report["plans"]


def test_profile_and_goals_consumed_without_guessing_unknown_task_type(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        path = "/planning-options?target_date=2026-10-14&horizon_days=7"
        before = get(c, path)
        profile(c, h)
        saved_goal = goal(c, h, ids["task"])
        after = get(c, path)
        assert after["profile_integration"] == "confirmed_profile_v1"
        assert after["goal_integration"] == "goal_budget_v1"
        assert after["preference_count"] == before["preference_count"] == 0

        def allocations(options):
            return [
                [
                    (b["starts_at"], b["ends_at"], b["task_id"], b["step_id"])
                    for b in o["blocks"]
                ]
                for o in options["options"]
            ]

        assert allocations(before) != allocations(after)  # focus45 changes blocks
        assert all(o["proposed_minutes"] == 60 for o in after["options"])
        assert after["profile_context"]["application"]["deferred_fields"] == {}
        assert after["profile_context"]["application"]["classification_count"] == 0
        assert (
            after["goal_allocation"]["task_goal_ids"][ids["task"]] == saved_goal["id"]
        )
        assert get(c, "/profile")["data"]["confirmed"]
        assert saved_goal["data"]["weekly_budget_minutes"] == 600
        assert saved_goal["capacity"]["weekly_available_minutes"] is None


def test_real_six_hour_week_and_ten_hour_goal_are_ready_for_capacity_adapter(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings = get(c, "/settings")
        settings["data"].update(
            study_windows=[{"start": "09:00", "end": "10:00"}], daily_limit_minutes=60
        )
        post(c, h, "/settings", settings, "PUT")
        protection = draft(
            c,
            h,
            recurrence="weekly",
            weekdays=[7],
            starts_at="2026-10-19T09:00:00+08:00",
            ends_at="2026-10-19T10:00:00+08:00",
        )
        assert confirm(c, h, protection).status_code == 200
        saved_goal = goal(c, h)
        capacity = get(c, "/planning-capacity?target_date=2026-10-19&horizon_days=7")
        assert capacity["capacity_upper_bound_minutes"] == 360
        assert (
            saved_goal["data"]["weekly_budget_minutes"]
            - capacity["capacity_upper_bound_minutes"]
            == 240
        )
        # These real facts can be consumed by a future adapter. The product
        # correctly still declares its target-capacity view unknown today.
        assert get(c, "/goals")["goals"][0]["capacity"]["status"] == "unknown"
