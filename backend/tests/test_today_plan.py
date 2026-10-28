"""Today is a bounded, reviewed operation; all fixtures are synthetic."""

from copy import deepcopy
from datetime import datetime

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app import planner
from app.planner import build_plan, instant
from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login
from tests.test_planner import fixture
from tests.test_scheduling_constraints import confirm, resources, seed_work, write


def today_input():
    p = fixture()
    p["scope"] = "today"
    return p


def block(identity, day=14, start="12:00", end="13:00", **changes):
    return dict(
        id=identity,
        task_id="t1",
        step_id="a",
        title=identity,
        starts_at=f"2026-10-{day}T{start}:00+08:00",
        ends_at=f"2026-10-{day}T{end}:00+08:00",
        locked=False,
        status="suggested",
        **changes,
    )


def test_today_only_remaining_minutes_courses_constraints_and_capacity():
    p = today_input()
    p["now_utc"] = datetime.fromisoformat("2026-10-14T10:30:31+08:00")
    p["settings"]["daily_limit_minutes"] = 600
    p["steps"][0]["data"]["estimated_minutes"] = 600
    p["tasks"][0]["data"]["due_at"] = "2026-10-17T18:00:00+08:00"
    r = build_plan(p)
    assert r == build_plan(deepcopy(p))
    assert r["unscheduled"] and any(
        "未自动延至明天" in x["reason"] for x in r["unscheduled"]
    )
    assert all(
        instant(b["starts_at"]) >= instant("2026-10-14T11:10:00+08:00")
        and instant(b["ends_at"]) <= instant("2026-10-14T18:00:00+08:00")
        for b in r["blocks"]
    )


@pytest.mark.parametrize(
    "outside",
    [
        block("tomorrow", day=15),
        block("tomorrow-conflict", day=15, start="02:00", end="03:00"),
        block("yesterday", day=13),
        block("history", start="09:00", end="09:30"),
        block("ongoing", start="10:00", end="11:00"),
    ],
)
def test_history_other_dates_and_ongoing_are_never_removed(outside):
    p = today_input()
    p["preserved_blocks"] = [outside]
    p["current_blocks"] = deepcopy(p["preserved_blocks"])
    r = build_plan(p)
    assert outside in r["blocks"]
    assert not r["removed_blocks"]
    if outside["id"] in ("tomorrow", "tomorrow-conflict", "ongoing"):
        # Conflicts are reported rather than counted as valid completed work.
        assert r["warnings"] and r["unscheduled"]
        assert not any(
            x["id"] != outside["id"] and x["step_id"] == "a" for x in r["blocks"]
        )


def test_future_reserved_work_does_not_get_duplicated_today_or_unlock_early_dependency():
    p = today_input()
    p["tasks"][0]["data"]["due_at"] = None
    p["steps"][0]["data"]["estimated_minutes"] = 60
    future = block("tomorrow", day=15)
    p["preserved_blocks"] = [future]
    p["current_blocks"] = [future]
    r = build_plan(p)
    assert r["blocks"] == [future]
    assert r["unscheduled"][0]["step_id"] == "b"


def test_midnight_empty_window_and_missing_estimates_do_not_invent_work():
    p = today_input()
    p["now_utc"] = datetime.fromisoformat("2026-10-14T23:59:59+08:00")
    p["tasks"][0]["data"]["due_at"] = None
    r = build_plan(p)
    assert r["blocks"] == [] and len(r["unscheduled"]) == 2
    p["steps"] = []
    assert build_plan(p)["unscheduled"][0]["remaining_minutes"] is None
    p["tasks"] = []
    assert build_plan(p)["unscheduled"] == []


def test_today_rounds_start_up_to_next_minute():
    p = today_input()
    p["occurrences"] = []
    p["now_utc"] = datetime.fromisoformat("2026-10-14T10:30:31+08:00")
    assert instant(build_plan(p)["blocks"][0]["starts_at"]) == instant(
        "2026-10-14T10:31:00+08:00"
    )


def test_today_confirm_preserves_rows_and_rejects_late_stale_and_cross_midnight(
    tmp_path, monkeypatch
):
    clock = [datetime.fromisoformat("2026-10-14T08:00:00+08:00")]
    monkeypatch.setattr(planner, "now", lambda: clock[0])
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        # Generate all work on tomorrow, then today's mode must keep those exact rows.
        tomorrow = write(
            c, h, "/plan-drafts", {"target_date": "2026-10-15", "horizon_days": 1}
        ).json()
        # Seed work is due today, so first extend its deadline through the public task API.
        task = c.get("/api/tasks").json()[0]
        response = write(
            c,
            h,
            f"/tasks/{task['id']}",
            {"revision": task["revision"], "due_at": "2026-10-17T18:00:00+08:00"},
            "PATCH",
        )
        assert response.status_code == 200, response.text
        tomorrow = write(
            c, h, "/plan-drafts", {"target_date": "2026-10-15", "horizon_days": 1}
        ).json()
        assert confirm(c, h, tomorrow).status_code == 200
        before = c.get("/api/plan-blocks").json()
        assert before
        d = write(c, h, "/plan-drafts", {"scope": "today"}, key="today")
        assert d.status_code == 200, d.text
        assert (
            write(c, h, "/plan-drafts", {"scope": "today"}, key="today").json()
            == d.json()
        )
        assert c.get("/api/plan-blocks").json() == before
        assert d.json()["data"]["payload"]["scope"] == "today"
        assert confirm(c, h, d.json()).status_code == 200
        assert c.get("/api/plan-blocks").json() == before
        # Past/current facts survive another today confirmation without revision changes.
        clock[0] = datetime.fromisoformat("2026-10-15T10:30:00+08:00")
        d = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        assert confirm(c, h, d).status_code == 200
        after = {b["id"]: b for b in c.get("/api/plan-blocks").json()}
        for b in before:
            if instant(b["data"]["starts_at"]) < clock[0]:
                assert after[b["id"]] == b
        d = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        clock[0] = datetime.fromisoformat("2026-10-16T00:00:00+08:00")
        assert confirm(c, h, d).status_code == 409


def test_today_server_timezone_replay_stale_and_past_new_start(tmp_path, monkeypatch):
    clock = [datetime.fromisoformat("2026-10-13T23:30:00Z")]
    monkeypatch.setattr(planner, "now", lambda: clock[0])
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        d = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        assert d["data"]["payload"]["target_date"] == "2026-10-14"
        assert d["data"]["payload"]["horizon_days"] == 1
        assert c.get("/api/plan-blocks").json() == []
        assert d["data"]["payload"]["blocks"]
        # Waiting beyond the first suggested start cannot write an already-past plan.
        clock[0] = datetime.fromisoformat("2026-10-14T10:31:00+08:00")
        assert confirm(c, h, d).status_code == 409
        assert not resources(c, "plan_snapshot")
        d = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        settings = c.get("/api/settings").json()
        settings["data"]["daily_limit_minutes"] = 120
        assert write(c, h, "/settings", settings, "PUT").status_code == 200
        assert confirm(c, h, d).status_code == 409
        assert not c.get("/api/plan-blocks").json()
        for body in [
            {"scope": "today", "horizon_days": 7},
            {"scope": "today", "target_date": "2026-10-14"},
        ]:
            assert write(c, h, "/plan-drafts", body).status_code == 422


class TodayModel(ToolModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            return super()._generate(messages, stop, run_manager, **kwargs)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "propose_daily_plan",
                                "args": {},
                                "id": "today",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


def test_assistant_daily_tool_defaults_to_today_and_never_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2026-10-14T08:00:00+08:00")
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        c.app.state.agent_model_factory = lambda: TodayModel()
        t = write(c, h, "/agent/threads", {}).json()
        r = write(
            c, h, "/agent/runs", {"thread_id": t["id"], "message": "安排今天剩余的时间"}
        ).json()
        assert wait_run(c, r["id"])["data"]["status"] == "done"
        d = c.get("/api/drafts").json()[-1]
        assert d["data"]["payload"]["scope"] == "today"
        assert not c.get("/api/plan-blocks").json()


def test_completed_locked_and_replaced_today_survive_restart_exactly(
    tmp_path, monkeypatch
):
    clock = [datetime.fromisoformat("2026-10-14T08:00:00+08:00")]
    monkeypatch.setattr(planner, "now", lambda: clock[0])
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        first = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        assert confirm(c, h, first).status_code == 200
        blocks = c.get("/api/plan-blocks").json()
        completed, locked = blocks[:2]
        completed = write(
            c,
            h,
            f"/plan-blocks/{completed['id']}",
            {"revision": completed["revision"], "completed": True},
            "PATCH",
        ).json()
        locked = write(
            c,
            h,
            f"/plan-blocks/{locked['id']}",
            {"revision": locked["revision"], "locked": True},
            "PATCH",
        ).json()
        # Changed windows may remove unlocked future suggestions, but never these facts.
        settings = c.get("/api/settings").json()
        settings["data"]["study_windows"] = [{"start": "16:00", "end": "18:00"}]
        assert write(c, h, "/settings", settings, "PUT").status_code == 200
        d = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        assert d["data"]["payload"]["removed_blocks"]
        previous = c.get("/api/plan-blocks").json()
        # A block proposed for removal may have started during review.
        removed = d["data"]["payload"]["removed_blocks"][0]["id"]
        clock[0] = instant(
            next(b["data"]["starts_at"] for b in previous if b["id"] == removed)
        )
        from datetime import timedelta

        clock[0] += timedelta(seconds=1)
        assert confirm(c, h, d).status_code == 409
        assert c.get("/api/plan-blocks").json() == previous
        d = write(c, h, "/plan-drafts", {"scope": "today"}).json()
        assert confirm(c, h, d, key="save-today").status_code == 200
        assert confirm(c, h, d, key="save-today").status_code == 200
        after = {b["id"]: b for b in c.get("/api/plan-blocks").json()}
        assert after[completed["id"]] == completed
        assert after[locked["id"]] == locked
        cookie = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert {b["id"]: b for b in c.get("/api/plan-blocks").json()} == after
