"""B notification lifecycle with isolated SQLite and the actual A planner."""

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import planner
from app.contracts import StudentSettings
from app.db import Base, Receipt, Resource

CLOCK = datetime.fromisoformat("2026-10-29T09:00:00+08:00")


def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/proactive.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.sessions = sessions

    async def get_db():
        async with sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def user(x_test_owner: str | None = Header(default=None)):
        if not x_test_owner:
            raise HTTPException(401)
        return SimpleNamespace(id=x_test_owner)

    from app.proactive_routes import proactive_router

    app.include_router(proactive_router(get_db, user))
    return TestClient(app)


def headers(key="write", owner="alice"):
    return {"X-Test-Owner": owner, "Idempotency-Key": key}


def call_db(c, fn):
    async def run():
        async with c.app.state.sessions() as db:
            result = await fn(db)
            await db.commit()
            return result

    return c.portal.call(run)


def rows(c, kind=None):
    async def read(db):
        query = select(Resource)
        if kind:
            query = query.where(Resource.kind == kind)
        return list((await db.scalars(query)).all())

    return call_db(c, read)


def seed(c, minutes=60, window_end="10:20", owner="alice", estimated=True):
    async def write(db):
        settings = StudentSettings(
            week1_monday="2026-10-26",
            study_windows=[{"start": "10:00", "end": window_end}],
            daily_limit_minutes=60,
            min_block_minutes=5,
            buffer_minutes=0,
        ).model_dump(mode="json")
        db.add(
            Resource(
                id=f"settings-{owner}", owner_id=owner, kind="settings", data=settings
            )
        )
        db.add(
            Resource(
                id=f"task-{owner}",
                owner_id=owner,
                kind="task",
                data={
                    "title": "作业",
                    "status": "open",
                    "priority": 3,
                    "due_at": "2026-10-29T11:00:00+08:00",
                },
            )
        )
        if estimated:
            db.add(
                Resource(
                    id=f"step-{owner}",
                    owner_id=owner,
                    kind="step",
                    data={
                        "task_id": f"task-{owner}",
                        "title": "写第一节",
                        "status": "open",
                        "estimated_minutes": minutes,
                        "spent_minutes": 0,
                        "dependency_ids": [],
                    },
                )
            )

    call_db(c, write)


def change(c, rid, patch):
    async def write(db):
        r = await db.get(Resource, rid)
        r.data = {**r.data, **patch}
        r.revision += 1
        settings = await db.get(Resource, "settings-alice")
        if settings.id != rid:
            settings.revision += 1

    call_db(c, write)


def enable(c, **patch):
    current = c.get("/api/proactive/preferences", headers=headers()).json()
    data = {**current["data"], "enabled": True, **patch}
    response = c.put(
        "/api/proactive/preferences",
        json={"revision": current["revision"], "data": data},
        headers=headers(f"preferences-{current['revision']}"),
    )
    assert response.status_code == 200, response.text
    return response.json()


def refresh(c, key="refresh", owner="alice", active=True):
    response = c.post(
        "/api/proactive/refresh",
        json={"app_active": active},
        headers=headers(key, owner),
    )
    assert response.status_code == 200, response.text
    return response.json()


def suggestion(result, category="deadline"):
    return next(
        r
        for r in result["suggestions"]
        if r["data"]["category"] == category
        and r["data"]["state"] not in {"resolved", "superseded"}
    )


def action(c, item, kind="dismiss", key="action", owner="alice", **extra):
    return c.post(
        f"/api/proactive/suggestions/{item['id']}/actions",
        json={
            "revision": item["revision"],
            "fingerprint": item["data"]["fingerprint"],
            "action": kind,
            **extra,
        },
        headers=headers(key, owner),
    )


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    from app import proactive

    monkeypatch.setattr(planner, "now", lambda: CLOCK)
    monkeypatch.setattr(proactive, "now", lambda: CLOCK)


def test_defaults_readonly_and_refresh_requires_active_opt_in(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/api/proactive/preferences").status_code == 401
        data = c.get("/api/proactive/preferences", headers=headers()).json()
        assert data["revision"] == 0 and data["data"]["enabled"] is False
        assert data["data"]["quiet_hours"] is None and data["data"]["timezone"] is None
        assert refresh(c)["suppression"] == "disabled"
        assert rows(c) == []
        enable(c)
        assert refresh(c, "inactive", active=False)["suppression"] == "inactive"
        assert not rows(c, "settings")


def test_real_A_risk_capacity_and_20minute_window_no_schedule_writes(tmp_path):
    with client(tmp_path) as c:
        seed(c)
        enable(c)
        result = refresh(c)
        risk = suggestion(result)
        assert risk["data"]["evidence"]["risk"]["remaining_minutes"] == 40
        assert risk["data"]["sources"][0]["id"] == "task-alice"
        window = suggestion(result, "available_window")["data"]["evidence"][
            "free_window"
        ]
        assert window["minutes"] == 20
        assert (
            datetime.fromisoformat(window["ends_at"])
            - datetime.fromisoformat(window["starts_at"])
        ).total_seconds() >= 1200
        assert result["capacity"]["unallocated_minutes"] == 40
        assert "实际投入未知" in " ".join(risk["data"]["gaps"])
        assert not rows(c, "draft") and not rows(c, "plan_block")
        assert (
            c.get("/api/proactive/suggestions", headers=headers(owner="bob")).json()[
                "suggestions"
            ]
            == []
        )
        assert action(c, risk, owner="bob").status_code == 404


def test_dedup_unrelated_revision_and_dismiss_persist_across_restart(tmp_path):
    with client(tmp_path) as c:
        seed(c)
        enable(c)
        first = suggestion(refresh(c))
        assert action(c, first).status_code == 200
        change(c, "settings-alice", {"semester_name": "只改学期名称"})
        after = suggestion(refresh(c, "second"))
        assert after["id"] == first["id"] and after["data"]["state"] == "dismissed"
        assert (
            len(
                [
                    r
                    for r in rows(c, "proactive_suggestion")
                    if r.data["category"] == "deadline"
                ]
            )
            == 1
        )
    with client(tmp_path) as restarted:
        persisted = suggestion(refresh(restarted, "after-restart"))
        assert (
            persisted["id"] == first["id"] and persisted["data"]["state"] == "dismissed"
        )


def test_changed_resolved_and_recur_start_new_episode(tmp_path):
    with client(tmp_path) as c:
        seed(c)
        enable(c)
        first = suggestion(refresh(c))
        action(c, first)
        change(c, "step-alice", {"estimated_minutes": 90})
        second = suggestion(refresh(c, "changed"))
        assert second["id"] != first["id"] and second["data"]["state"] == "pending"
        change(c, "task-alice", {"status": "completed"})
        resolved = refresh(c, "resolved")
        assert not any(r["data"]["visible"] for r in resolved["suggestions"])
        change(c, "task-alice", {"status": "open"})
        third = suggestion(refresh(c, "recur"))
        assert third["id"] != second["id"] and third["data"]["state"] == "pending"


def test_snooze_suppression_and_return_after_elapsed_time(tmp_path, monkeypatch):
    from app import proactive

    with client(tmp_path) as c:
        seed(c)
        enable(c)
        first = suggestion(refresh(c))
        response = action(c, first, "snooze", snooze_minutes=30)
        assert response.status_code == 200, response.text
        assert suggestion(refresh(c, "snoozed"))["data"]["state"] == "snoozed"
        later = datetime.fromisoformat("2026-10-29T09:31:00+08:00")
        monkeypatch.setattr(proactive, "now", lambda: later)
        monkeypatch.setattr(planner, "now", lambda: later)
        returned = suggestion(refresh(c, "expired"))
        assert returned["id"] == first["id"] and returned["data"]["visible"]


def test_quiet_overnight_start_weekday_and_DST_instants(tmp_path):
    from app.proactive import quiet_at

    quiet = [{"weekdays": [7], "start": "22:00", "end": "02:00"}]
    assert quiet_at(
        {"timezone": "Asia/Shanghai", "quiet_hours": quiet},
        datetime.fromisoformat("2026-11-02T01:00:00+08:00"),
    )
    assert not quiet_at(
        {"timezone": "Asia/Shanghai", "quiet_hours": quiet},
        datetime.fromisoformat("2026-11-02T22:30:00+08:00"),
    )
    dst = {
        "timezone": "America/New_York",
        "quiet_hours": [{"weekdays": [7], "start": "01:00", "end": "02:00"}],
    }
    assert quiet_at(dst, datetime.fromisoformat("2026-11-01T01:30:00-04:00"))
    assert quiet_at(dst, datetime.fromisoformat("2026-11-01T01:30:00-05:00"))
    with client(tmp_path) as c:
        seed(c)
        enable(
            c,
            timezone="Asia/Shanghai",
            quiet_hours=[{"weekdays": [4], "start": "08:00", "end": "10:00"}],
        )
        result = refresh(c)
        assert result["suppression"] == "quiet_hours"
        assert not any(r["data"]["visible"] for r in result["suggestions"])


def test_disabled_category_and_no_fabricated_window_or_work(tmp_path):
    with client(tmp_path) as c:
        seed(c, window_end="10:19")
        enable(c)
        result = refresh(c)
        assert not any(
            r["data"]["category"] == "available_window" for r in result["suggestions"]
        )
        risk = suggestion(result)
        assert action(c, risk, "disable_category").status_code == 200
        assert not suggestion(refresh(c, "disabled"))["data"]["visible"]
        change(c, "task-alice", {"status": "completed"})
        change(
            c,
            "settings-alice",
            {"study_windows": [{"start": "10:00:00", "end": "11:00:00"}]},
        )
        assert not any(
            r["data"]["visible"] for r in refresh(c, "no-work")["suggestions"]
        )


def test_new_action_rechecks_source_but_committed_receipt_replays_historical_result(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(c)
        enable(c)
        item = suggestion(refresh(c))
        response = action(c, item)
        assert response.status_code == 200
        assert action(c, item).json() == response.json()
        assert action(c, item, "snooze", snooze_minutes=30).status_code == 409
        change(c, "step-alice", {"estimated_minutes": 90})
        assert action(c, item).json() == response.json()
        assert action(c, item, key="new-stale").status_code == 409
        assert not rows(c, "draft") and not rows(c, "plan_block")


def test_accept_details_and_real_original_replan_draft_are_not_formal_writes(tmp_path):
    with client(tmp_path) as c:
        seed(c)
        enable(c)
        result = refresh(c)
        details = action(c, suggestion(result), "accept", accept_mode="details")
        assert details.status_code == 200, details.text
        assert details.json()["open_task_id"] == "task-alice"
        window = suggestion(result, "available_window")
        draft = action(c, window, "accept", key="draft", accept_mode="replan")
        assert draft.status_code == 200, draft.text
        draft_id = draft.json()["draft"]["id"]
        assert draft.json()["requires_confirmation"] is True
        assert rows(c, "draft")[0].id == draft_id
        assert not rows(c, "plan_block")
        replay = action(c, window, "accept", key="draft", accept_mode="replan")
        assert replay.json() == draft.json() and len(rows(c, "draft")) == 1
        change(c, "settings-alice", {"semester_name": "source changed"})
        assert (
            action(c, window, "accept", key="draft", accept_mode="replan").json()
            == draft.json()
        )


def test_unknown_estimate_and_validation(tmp_path):
    with client(tmp_path) as c:
        seed(c, estimated=False)
        enable(c)
        item = suggestion(refresh(c), "unknown_estimate")
        assert item["data"]["evidence"]["risk"]["remaining_minutes"] is None
        assert item["data"]["evidence"]["risk"]["code"] == "unknown_estimate"
        for patch in [
            {"timezone": "Bad/Zone"},
            {"quiet_hours": [{"weekdays": [0], "start": "22:00", "end": "07:00"}]},
            {"quiet_hours": [{"weekdays": [1], "start": "22:00", "end": "22:00"}]},
        ]:
            data = {
                **c.get("/api/proactive/preferences", headers=headers()).json()["data"],
                **patch,
            }
            assert (
                c.put(
                    "/api/proactive/preferences",
                    json={"revision": 1, "data": data},
                    headers=headers("invalid"),
                ).status_code
                == 422
            )
        assert action(c, item, "snooze", snooze_minutes=0).status_code == 422


def test_risk_order_uses_confirmed_deadline_before_priority_and_shows_dependencies(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(c, window_end="10:19")

        async def write(db):
            earlier = {
                "title": "较早截止",
                "status": "open",
                "priority": 1,
                "due_at": "2026-10-29T09:30:00+08:00",
            }
            db.add(
                Resource(id="early-task", owner_id="alice", kind="task", data=earlier)
            )
            db.add(
                Resource(
                    id="early-step",
                    owner_id="alice",
                    kind="step",
                    data={
                        "task_id": "early-task",
                        "title": "早任务步骤",
                        "status": "open",
                        "estimated_minutes": 60,
                        "spent_minutes": 0,
                        "dependency_ids": ["step-alice"],
                    },
                )
            )

        call_db(c, write)
        enable(c)
        risks = [
            r for r in refresh(c)["suggestions"] if r["data"]["category"] == "deadline"
        ]
        assert [r["data"]["task_id"] for r in risks] == ["early-task", "task-alice"]
        assert risks[0]["data"]["evidence"]["dependency_ids"] == ["step-alice"]


def test_running_or_changed_original_plan_is_explained_without_execution_inference(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(c)

        async def write(db):
            db.add(
                Resource(
                    id="running-block",
                    owner_id="alice",
                    kind="plan_block",
                    data={
                        "task_id": "task-alice",
                        "step_id": "step-alice",
                        "title": "正在运行的原安排",
                        "starts_at": "2026-10-29T08:30:00+08:00",
                        "ends_at": "2026-10-29T09:30:00+08:00",
                        "status": "suggested",
                        "locked": False,
                    },
                )
            )

        call_db(c, write)
        enable(c)
        original = rows(c, "plan_block")[0]
        result = refresh(c)
        item = suggestion(result, "facts_changed")
        assert any("实际投入" in reason for reason in item["data"]["reasons"])
        assert any(s["id"] == "running-block" for s in item["data"]["sources"])
        assert rows(c, "plan_block")[0].data == original.data
        assert not rows(c, "execution_record") and not rows(c, "draft")


def test_proactive_event_receipt_and_settings_rollback_together(tmp_path, monkeypatch):
    from app import proactive

    with client(tmp_path) as c:
        seed(c)
        enable(c)
        item = suggestion(refresh(c))
        original = c.get("/api/proactive/preferences", headers=headers()).json()

        async def fail(*args, **kwargs):
            raise RuntimeError("proactive action event failed")

        monkeypatch.setattr(proactive, "record_change", fail)
        with pytest.raises(RuntimeError, match="proactive action event"):
            action(c, item, "disable_category")
        assert c.get("/api/proactive/preferences", headers=headers()).json() == original
        assert (
            suggestion(c.get("/api/proactive/suggestions", headers=headers()).json())[
                "data"
            ]["state"]
            == "pending"
        )

        async def read(db):
            return len(list((await db.scalars(select(Receipt))).all()))

        assert call_db(c, read) == 1


def test_clock_tick_and_unrelated_global_revision_do_not_realert_window(
    tmp_path, monkeypatch
):
    from app import proactive

    with client(tmp_path) as c:
        seed(c, window_end="11:00")
        enable(c)
        first = suggestion(refresh(c), "available_window")
        assert action(c, first).status_code == 200
        change(c, "settings-alice", {"semester_name": "无关名称"})
        after = suggestion(refresh(c, "unrelated-window"), "available_window")
        assert after["id"] == first["id"] and after["data"]["state"] == "dismissed"
        later = datetime.fromisoformat("2026-10-29T10:01:00+08:00")
        monkeypatch.setattr(proactive, "now", lambda: later)
        monkeypatch.setattr(planner, "now", lambda: later)
        tick = suggestion(refresh(c, "tick"), "available_window")
        assert tick["id"] == first["id"] and tick["data"]["state"] == "dismissed"


def test_three_upcoming_deadlines_use_confirmed_facts_even_when_A_can_fit_all_work(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(c, minutes=20, window_end="12:00")

        async def write(db):
            for key, due in [("late", "12:00"), ("middle", "11:30")]:
                db.add(
                    Resource(
                        id=f"{key}-task",
                        owner_id="alice",
                        kind="task",
                        data={
                            "title": f"{key}作业",
                            "status": "open",
                            "priority": 2,
                            "due_at": f"2026-10-29T{due}:00+08:00",
                        },
                    )
                )
                db.add(
                    Resource(
                        id=f"{key}-step",
                        owner_id="alice",
                        kind="step",
                        data={
                            "task_id": f"{key}-task",
                            "title": "准备提交",
                            "status": "open",
                            "estimated_minutes": 20,
                            "spent_minutes": 0,
                            "dependency_ids": [],
                        },
                    )
                )

        call_db(c, write)
        enable(c)
        result = refresh(c)
        assert result["capacity"]["unallocated_minutes"] == 0
        upcoming = [
            r for r in result["suggestions"] if r["data"]["category"] == "deadline"
        ]
        assert [r["data"]["task_id"] for r in upcoming] == [
            "task-alice",
            "middle-task",
            "late-task",
        ]
        assert all(
            r["data"]["evidence"]["trigger"] == "confirmed_deadline_within_48h"
            for r in upcoming
        )
        assert all("实际投入未知" in " ".join(r["data"]["gaps"]) for r in upcoming)


def test_nested_categories_and_weekdays_require_exact_types(tmp_path):
    with client(tmp_path) as c:
        current = c.get("/api/proactive/preferences", headers=headers()).json()
        for patch in [
            {"categories": {**current["data"]["categories"], "deadline": 1}},
            {
                "timezone": "Asia/Shanghai",
                "quiet_hours": [{"weekdays": [True], "start": "22:00", "end": "07:00"}],
            },
            {
                "timezone": "Asia/Shanghai",
                "quiet_hours": [{"weekdays": ["1"], "start": "22:00", "end": "07:00"}],
            },
        ]:
            response = c.put(
                "/api/proactive/preferences",
                json={"revision": 0, "data": {**current["data"], **patch}},
                headers=headers(),
            )
            assert response.status_code == 422, response.text
        assert not rows(c)
