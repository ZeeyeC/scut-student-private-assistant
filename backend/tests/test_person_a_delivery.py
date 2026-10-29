"""A's real B adapters and generators. Isolated synthetic data, no model calls."""

from copy import deepcopy
from datetime import timedelta

import pytest

from app import planner
from app.planner import build_plan, instant
from tests.test_ab_integration import get, goal, plan, post
from tests.test_execution import correction, execution_body, save, seed_execution
from tests.test_foundation import make_client, register_login
from tests.test_planning_workbench import preferred_input
from tests.test_scheduling_constraints import confirm, resources, seed_work, write


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(planner, "now", lambda: instant("2026-10-14T08:00:00+08:00"))


def capacity(c):
    return get(c, "/planning-capacity?target_date=2026-10-14&horizon_days=1")


@pytest.mark.parametrize("minutes", [None, 0, 25])
def test_execution_unknown_zero_real_and_no_projection_double_count(tmp_path, minutes):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c, spent=10)
        if minutes is not None:
            save(
                c,
                h,
                execution_body(
                    c, ids, actual_minutes=minutes, legacy_resolution="separate"
                ),
            )
        value = capacity(c)
        basis = value["execution_context"]["steps"][ids["step"]]
        assert basis["actual_minutes"] == minutes
        assert basis["legacy_estimated_minutes"] == 10
        assert value["required_minutes"] == 60 - 10 - (minutes or 0)
        assert bool(basis["unknown_step_ids"]) == (minutes is None)
        assert basis["planning_spent_minutes"] == 10 + (minutes or 0)


def test_effective_correction_facts_propagate_to_all_reports(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        record = save(c, h, execution_body(c, ids))
        old = plan(c, h)
        updated = post(
            c, h, f"/executions/{record['id']}/corrections", correction(c, ids)
        )
        assert confirm(c, h, old).status_code == 409
        report = capacity(c)
        assert report["required_minutes"] == 40
        basis = report["execution_context"]["steps"][ids["step"]]
        assert basis["effective_record_ids"] == [updated["id"]]
        risks = get(c, "/planning-risks?target_date=2026-10-14&horizon_days=1")
        assert risks["execution_context"] == report["execution_context"]
        draft = plan(c, h, repair=True)
        assert (
            draft["data"]["payload"]["execution_context"] == report["execution_context"]
        )


def personal(p, **preferences):
    p["constraints"] = []
    p["profile_context"] = {
        "id": "profile",
        "revision": 2,
        "data": {
            "confirmed": True,
            "source": "user",
            "timezone": "Asia/Shanghai",
            "effective_from": None,
            "effective_until": None,
            "preferences": preferences,
        },
    }
    return p


def test_profile_windows_timezone_expiry_and_unknown_do_not_leave_hidden_habits():
    p = personal(
        preferred_input(),
        preferred_study_windows=[
            {"weekdays": [3], "start": "08:00", "end": "09:00", "task_type": "any"}
        ],
    )
    p["profile_context"]["data"]["timezone"] = "UTC"
    p["planning_strategy"] = "preferred"
    assert instant(build_plan(p)["blocks"][0]["starts_at"]) == instant(
        "2026-10-14T16:00:00+08:00"
    )
    for changes in (
        {"confirmed": False},
        {"effective_until": "2026-10-13"},
        {"effective_from": "2026-10-15"},
    ):
        copy = deepcopy(p)
        copy["profile_context"]["data"].update(changes)
        assert instant(build_plan(copy)["blocks"][0]["starts_at"]) == instant(
            "2026-10-14T09:00:00+08:00"
        )
    p["profile_context"]["data"]["preferences"]["preferred_study_windows"] = []
    assert instant(build_plan(p)["blocks"][0]["starts_at"]) == instant(
        "2026-10-14T09:00:00+08:00"
    )


def test_profile_focus_rest_load_and_zero_are_explicit_soft_inputs():
    p = personal(
        preferred_input(), focus_minutes=25, break_minutes=10, daily_load_minutes=50
    )
    p["steps"][0]["data"]["estimated_minutes"] = 90
    result = build_plan(p)
    assert result["capacity"]["proposed_minutes"] == 50
    a, b = result["blocks"]
    assert instant(b["starts_at"]) - instant(a["ends_at"]) == timedelta(minutes=10)
    assert "档案" in " ".join(a["explanation"]["reasons"])
    p["profile_context"]["data"]["preferences"]["daily_load_minutes"] = 0
    assert build_plan(p)["capacity"]["proposed_minutes"] == 0
    p["profile_context"]["data"]["preferences"]["daily_load_minutes"] = None
    assert build_plan(p)["capacity"]["proposed_minutes"] == 90


def goal_context(p, budget=60, adjustment="reduce", paused=False):
    p["goal_context"] = {
        "goals": [
            {
                "id": "goal1",
                "revision": 1,
                "data": {
                    "title": "真实关联目标",
                    "priority": 3,
                    "deadline": None,
                    "paused": paused,
                    "weekly_budget_minutes": budget,
                    "allowed_adjustment": adjustment,
                    "subtasks": [{"task_id": "t1", "status": "open"}],
                },
            }
        ]
    }
    return p


@pytest.mark.parametrize(
    "adjustment,allocated", [("reduce", 30), ("delay", 30), ("ask", 0)]
)
def test_goal_shared_budget_and_asking_never_silently_reduces(adjustment, allocated):
    p = goal_context(preferred_input(), 30, adjustment)
    p["constraints"] = []
    result = build_plan(p)
    assert result["capacity"]["proposed_minutes"] == allocated
    assert result["goal_allocation"]["weeks"][0]["planned_minutes"] == allocated
    assert p["tasks"][0]["data"]["due_at"] == "2026-10-14T18:00:00+08:00"
    if adjustment == "ask":
        assert "询问" in result["unscheduled"][0]["reason"]


def test_goal_dedup_pause_and_priority_share_one_capacity():
    p = goal_context(preferred_input(), 600)
    second = deepcopy(p["goal_context"]["goals"][0])
    second["id"] = "goal2"
    second["data"]["priority"] = 1
    p["goal_context"]["goals"].append(second)
    result = build_plan(p)
    assert result["goal_allocation"]["task_goal_ids"] == {"t1": "goal1"}
    assert sum(w["planned_minutes"] for w in result["goal_allocation"]["weeks"]) == 60
    p["goal_context"]["goals"][0]["data"]["paused"] = True
    p["goal_context"]["goals"][1]["data"]["paused"] = True
    result = build_plan(p)
    assert result["goal_allocation"]["weeks"] == []
    assert result["capacity"]["proposed_minutes"] == 60  # independently existing task


def test_two_goals_cannot_both_claim_six_hours():
    p = goal_context(preferred_input(), 300)
    p["constraints"] = []
    p["settings"]["daily_limit_minutes"] = 360
    p["settings"]["study_windows"] = [{"start": "09:00", "end": "15:00"}]
    p["steps"][0]["data"]["estimated_minutes"] = 300
    task, step, g = (
        deepcopy(p["tasks"][0]),
        deepcopy(p["steps"][0]),
        deepcopy(p["goal_context"]["goals"][0]),
    )
    task["id"], step["id"], step["data"]["task_id"], g["id"] = "t2", "s2", "t2", "goal2"
    g["data"]["subtasks"][0]["task_id"] = "t2"
    p["tasks"].append(task)
    p["steps"].append(step)
    p["goal_context"]["goals"].append(g)
    result = build_plan(p)
    weeks = result["goal_allocation"]["weeks"]
    assert sum(w["planned_minutes"] for w in weeks) == 360
    assert sum(w["unmet_budget_minutes"] for w in weeks) == 240


def test_notice_consume_dedup_lifecycle_versions_and_confirm_no_loop(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        before = get(c, "/plan-blocks")
        first = post(c, h, "/replanning/changes", {"app_active": True})
        notice = first["notice"]
        assert notice["data"]["state"] == "pending"
        assert get(c, "/plan-blocks") == before
        again = post(c, h, "/replanning/changes", {})
        assert again["consumed"] == 0 and again["notice"] == notice
        body = {
            "revision": notice["revision"],
            "source_revision": notice["data"]["source_revision"],
        }
        draft = write(c, h, "/replanning/changes/draft", body, key="notice-draft")
        assert draft.status_code == 200, draft.text
        assert (
            write(c, h, "/replanning/changes/draft", body, key="notice-draft").json()
            == draft.json()
        )
        assert confirm(c, h, draft.json()).status_code == 200
        assert get(c, "/replanning/changes")["data"]["state"] == "confirmed"
        for _ in range(2):
            assert post(c, h, "/replanning/changes", {})["consumed"] == 0
        assert len(resources(c, "replan_notice")) == 1


def test_notice_dismiss_replay_new_facts_stale_and_inactive_no_write(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_execution(c)
        notice = post(c, h, "/replanning/changes", {})["notice"]
        action = {
            "revision": notice["revision"],
            "source_revision": notice["data"]["source_revision"],
        }
        dismissed = write(c, h, "/replanning/changes/dismiss", action, key="dismiss")
        assert dismissed.status_code == 200
        assert (
            post(c, h, "/replanning/changes", {})["notice"]["data"]["state"]
            == "dismissed"
        )
        goal(c, h)
        assert get(c, "/replanning/changes")["data"]["state"] == "invalidated"
        assert write(c, h, "/replanning/changes/draft", action).status_code == 409
        before = get(c, "/data-export")
        assert post(c, h, "/replanning/changes", {"app_active": False})["consumed"] == 0
        assert get(c, "/data-export") == before
        assert post(c, h, "/replanning/changes", {})["consumed"] > 0
        assert (
            write(c, h, "/replanning/changes/dismiss", action, key="dismiss").json()
            == dismissed.json()
        )


def generate(c, h, key=None):
    return write(
        c,
        h,
        "/duration-suggestions/generate",
        {"expected_source_revision": get(c, "/settings")["revision"]},
        key=key,
    )


def observed_samples(c, h, ids):
    for i in range(3):
        save(
            c,
            h,
            execution_body(
                c,
                ids,
                plan_block_id=None,
                plan_block_revision=None,
                legacy_resolution="separate",
                actual_minutes=25,
                feedback="completed" if i == 2 else "partial",
            ),
        )


def act_duration(c, h, item, action, key=None):
    return write(
        c,
        h,
        f"/duration-suggestions/{item['id']}/actions",
        {
            "revision": item["revision"],
            "task_revision": item["current_task_revision"],
            "step_revision": item["current_step_revision"],
            "source_revision": item["current_source_revision"],
            "action": action,
        },
        key=key,
    )


def test_generator_end_to_end_accept_retry_restore_and_old_plan_stale(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        assert generate(c, h).json()["created_ids"] == []
        observed_samples(c, h, ids)
        old_plan = plan(c, h)
        generated = generate(c, h, "generate")
        assert generated.status_code == 200, generated.text
        body = generated.json()
        assert len(body["created_ids"]) == 1
        assert generate(c, h, "generate").json() == body
        item = body["result"]["suggestions"][0]
        assert item["data"]["suggested_minutes"] == 75
        assert item["data"]["default_estimated_minutes"] == 60
        assert generate(c, h).json()["created_ids"] == []
        assert (
            get(c, f"/tasks/{ids['task']}/steps")[0]["data"]["estimated_minutes"] == 60
        )
        applied = act_duration(c, h, item, "accept", "accept")
        assert applied.status_code == 200, applied.text
        assert applied.json()["step"]["data"]["estimated_minutes"] == 75
        assert act_duration(c, h, item, "accept", "accept").json() == applied.json()
        assert confirm(c, h, old_plan).status_code == 409
        restored = act_duration(c, h, applied.json()["suggestion"], "restore_default")
        assert (
            restored.status_code == 200
            and restored.json()["step"]["data"]["estimated_minutes"] == 60
        )
        assert generate(c, h).json()["created_ids"] == []


def test_generator_reject_does_not_reappear_but_correction_is_new_basis(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        observed_samples(c, h, ids)
        item = generate(c, h).json()["result"]["suggestions"][0]
        assert act_duration(c, h, item, "reject").status_code == 200

        goal(c, h)  # unrelated source revision must not revive rejected basis
        assert generate(c, h).json()["created_ids"] == []
        records = get(c, f"/tasks/{ids['task']}/executions")
        record = records[-1]
        post(
            c,
            h,
            f"/executions/{record['id']}/corrections",
            correction(c, ids, actual_minutes=30, feedback="completed"),
        )
        generated = generate(c, h).json()
        assert len(generated["created_ids"]) == 1
        assert len(generated["result"]["suggestions"][-1]["data"]["sample_basis"]) == 3
        assert generated["result"]["suggestions"][0]["freshness"] == "stale"


def test_new_resources_owner_isolation_and_atomic_generator_rollback(
    tmp_path, monkeypatch
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        observed_samples(c, h, ids)
        from app import duration_generator

        async def fail(*args):
            raise RuntimeError("synthetic rollback probe")

        original = duration_generator.list_suggestions
        monkeypatch.setattr(duration_generator, "list_suggestions", fail)
        with pytest.raises(RuntimeError, match="rollback"):
            generate(c, h, "rollback")
        assert resources(c, "duration_suggestion") == []
        monkeypatch.setattr(duration_generator, "list_suggestions", original)
        assert len(generate(c, h, "rollback").json()["created_ids"]) == 1
        post(c, h, "/replanning/changes", {})
        other = register_login(c, email="other-a@example.com")
        assert get(c, "/replanning/changes") is None
        assert get(c, "/duration-suggestions")["suggestions"] == []
        assert generate(c, other).json()["created_ids"] == []


def test_notice_restart_cursor_and_rollback(tmp_path, monkeypatch):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        original = planner.planning_result

        async def fail(*args, **kwargs):
            raise RuntimeError("synthetic consumer rollback")

        monkeypatch.setattr(planner, "planning_result", fail)
        before = get(c, "/data-export")["resources"]
        with pytest.raises(RuntimeError, match="rollback"):
            post(c, h, "/replanning/changes", {})
        assert get(c, "/data-export")["resources"] == before
        monkeypatch.setattr(planner, "planning_result", original)
        notice = post(c, h, "/replanning/changes", {})["notice"]
    with make_client(tmp_path) as c:
        token = get(c, "/csrf")["csrf_token"]
        assert (
            c.post(
                "/api/auth/login",
                data={
                    "username": "alice@example.com",
                    "password": "Student!Password2026",
                },
                headers={"Origin": "http://testserver", "X-CSRF-Token": token},
            ).status_code
            == 204
        )
        value = post(
            c,
            {"Origin": "http://testserver", "X-CSRF-Token": token},
            "/replanning/changes",
            {},
        )
        assert value["notice"] == notice and value["consumed"] == 0


def test_actual_completed_unknown_and_unassigned_records_are_not_zero(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        task = get(c, f"/tasks/{ids['task']}")
        post(
            c,
            h,
            f"/tasks/{ids['task']}",
            {"revision": task["revision"], "status": "completed"},
            "PATCH",
        )
        ctx = capacity(c)["execution_context"]
        assert ctx["tasks"][ids["task"]]["task_status"] == "completed"
        assert ctx["tasks"][ids["task"]]["actual_minutes"] is None
        task = get(c, f"/tasks/{ids['task']}")
        post(
            c,
            h,
            f"/tasks/{ids['task']}",
            {"revision": task["revision"], "status": "open"},
            "PATCH",
        )
        record = save(
            c,
            h,
            execution_body(
                c,
                ids,
                step_id=None,
                step_revision=None,
                plan_block_id=None,
                plan_block_revision=None,
            ),
        )
        ctx = capacity(c)["execution_context"]
        assert ctx["known_actual_minutes"] == 25 and ctx["actual_minutes"] is None
        assert ctx["tasks"][ids["task"]]["unassigned_record_ids"] == [record["id"]]
        assert capacity(c)["required_minutes"] == 60  # don't guess step attribution


def test_profile_review_interval_uses_course_basis_and_reset_invalidates(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        request = {
            "confirmed": True,
            "target_date": "2026-10-14",
            "horizon_days": 7,
            "review_minutes": 20,
        }
        before = post(c, h, "/daily-routine-preview", request)
        assert before["candidates"][0]["starts_at"].startswith("2026-10-14")
        profile = post(
            c,
            h,
            "/profile",
            {
                "revision": get(c, "/profile")["revision"],
                "data": {
                    "timezone": "Asia/Shanghai",
                    "preferences": {"review_interval_days": 1},
                },
            },
            "PUT",
        )
        preview = post(c, h, "/daily-routine-preview", request)
        assert preview["candidates"][0]["starts_at"].startswith("2026-10-15")
        candidate = preview["candidates"][0]
        draft = post(
            c,
            h,
            "/daily-routine-drafts",
            {
                "candidate_id": candidate["id"],
                "expected_source_revision": preview["source_revision"],
                "request": request,
            },
        )
        post(c, h, "/profile/reset", {"revision": profile["revision"]})
        assert confirm(c, h, draft).status_code == 409
        assert post(c, h, "/daily-routine-preview", request)["candidates"][0][
            "starts_at"
        ].startswith("2026-10-14")


def test_goal_counts_effective_observed_effort_once_and_respects_deadline(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        g = goal(c, h, ids["task"])
        g = post(
            c,
            h,
            f"/goals/{g['id']}",
            {
                "revision": g["revision"],
                "weekly_budget_minutes": 60,
                "deadline": "2026-10-14T09:20:00+08:00",
            },
            "PATCH",
        )
        record = save(c, h, execution_body(c, ids))
        result = capacity(c)
        week = result["goal_allocation"]["weeks"][0]
        assert week["known_actual_minutes"] == 25 and week["planned_minutes"] == 20
        assert week["unmet_budget_minutes"] == 15
        post(c, h, f"/executions/{record['id']}/corrections", correction(c, ids))
        assert capacity(c)["goal_allocation"]["weeks"][0]["known_actual_minutes"] == 20
        assert (
            get(c, f"/tasks/{ids['task']}")["data"]["due_at"]
            == "2026-12-31T22:00:00+08:00"
        )


@pytest.mark.parametrize(
    "value,feedback", [(0, "partial"), (100, "completed"), (25, "partial")]
)
def test_generator_insufficient_or_out_of_range_is_explicit(tmp_path, value, feedback):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        for _ in range(3):
            save(
                c,
                h,
                execution_body(
                    c,
                    ids,
                    plan_block_id=None,
                    plan_block_revision=None,
                    legacy_resolution="separate",
                    actual_minutes=value,
                    feedback=feedback,
                ),
            )
        result = generate(c, h).json()
        assert result["created_ids"] == [] and result["skipped"][0]["reason"]
        assert (
            get(c, f"/tasks/{ids['task']}/steps")[0]["data"]["estimated_minutes"] == 60
        )


def test_pending_duration_can_refresh_versions_without_reviving_rejected_basis(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        ids = seed_execution(c)
        observed_samples(c, h, ids)
        old = generate(c, h).json()["result"]["suggestions"][0]
        goal(c, h)
        assert get(c, "/duration-suggestions")["suggestions"][0]["freshness"] == "stale"
        current = generate(c, h).json()
        assert current["created_ids"] == [] and current["refreshed_ids"] == [old["id"]]
        item = current["result"]["suggestions"][0]
        assert item["freshness"] == "fresh" and item["revision"] > old["revision"]
        assert act_duration(c, h, old, "accept").status_code == 409
        assert act_duration(c, h, item, "reject").status_code == 200


def test_profile_rest_crossing_midnight_is_reserved_on_both_days():
    p = personal(preferred_input(), focus_minutes=25, break_minutes=30)
    p["now_utc"] = instant("2026-10-14T23:20:00+08:00")
    p["horizon_days"] = 2
    p["settings"]["study_windows"] = [
        {"start": "00:00", "end": "01:00"},
        {"start": "23:00", "end": "23:59"},
    ]
    p["tasks"][0]["data"]["due_at"] = "2026-10-15T02:00:00+08:00"
    blocks = build_plan(p)["blocks"]
    assert len(blocks) == 2
    assert instant(blocks[1]["starts_at"]) == instant("2026-10-15T00:15:00+08:00")
    assert instant(blocks[1]["starts_at"]) - instant(blocks[0]["ends_at"]) == timedelta(
        minutes=30
    )


def test_preferred_allocation_reserves_rest_before_later_blocks_too():
    p = personal(
        preferred_input(),
        focus_minutes=25,
        break_minutes=10,
        preferred_study_windows=[
            {"weekdays": [3], "start": "21:00", "end": "22:00", "task_type": "any"}
        ],
    )
    p["settings"]["study_windows"] = [{"start": "20:30", "end": "22:00"}]
    p["tasks"][0]["data"]["due_at"] = "2026-10-14T22:00:00+08:00"
    p["steps"][0]["data"]["estimated_minutes"] = 75
    p["planning_strategy"] = "preferred"
    result = build_plan(p)
    blocks = sorted(result["blocks"], key=lambda b: b["starts_at"])
    assert result["capacity"]["proposed_minutes"] <= 70
    assert all(
        instant(b["starts_at"]) - instant(a["ends_at"]) >= timedelta(minutes=10)
        for a, b in zip(blocks, blocks[1:])
    )
