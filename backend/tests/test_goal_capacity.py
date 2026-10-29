"""B5 consumes the real planner in an isolated database; no personal data."""

from contextlib import asynccontextmanager
from datetime import datetime
from importlib.util import find_spec
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.contracts import StudentSettings
from app.db import Base, Resource

CLOCK = datetime.fromisoformat("2026-10-29T02:00:00+00:00")


def linked_client(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/linked.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.sessions = sessions

    async def db_session():
        async with sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    async def current_user(x_test_owner: str | None = Header(default=None)):
        if not x_test_owner:
            raise HTTPException(401)
        return SimpleNamespace(id=x_test_owner)

    from app.goal_routes import goal_router
    from app.planner import planner_router
    from app.review_routes import review_router
    from app.routes import business_router

    app.include_router(review_router(db_session, current_user))
    app.include_router(goal_router(db_session, current_user))
    app.include_router(business_router(db_session, current_user))
    app.include_router(planner_router(db_session, current_user))
    if find_spec("app.goal_capacity_routes"):
        from app.goal_capacity_routes import goal_capacity_router

        app.include_router(goal_capacity_router(db_session, current_user))
    return TestClient(app)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    from app import planner, weekly_review

    monkeypatch.setattr(planner, "now", lambda: CLOCK)
    monkeypatch.setattr(weekly_review, "now", lambda: CLOCK)
    if find_spec("app.goal_capacity"):
        from app import goal_capacity

        monkeypatch.setattr(goal_capacity, "now", lambda: CLOCK)


def headers(key="one", owner="alice"):
    return {"X-Test-Owner": owner, "Idempotency-Key": key}


def seed(c, *rows):
    async def write():
        async with c.app.state.sessions() as db:
            db.add_all(
                [
                    Resource(id=rid, kind=kind, data=data, owner_id=owner)
                    for rid, kind, data, owner in rows
                ]
            )
            await db.commit()

    c.portal.call(write)


def resources(c, kind=None, owner="alice"):
    async def read():
        async with c.app.state.sessions() as db:
            query = select(Resource).where(Resource.owner_id == owner)
            if kind:
                query = query.where(Resource.kind == kind)
            return [(r.id, r.revision, r.data) for r in (await db.scalars(query)).all()]

    return c.portal.call(read)


def settings(owner="alice"):
    return (
        f"settings-{owner}",
        "settings",
        StudentSettings(
            study_windows=[{"start": "09:00", "end": "10:00"}],
            daily_limit_minutes=60,
            buffer_minutes=0,
        ).model_dump(mode="json"),
        owner,
    )


def goal(c, title, budget, paused=False, completed=False, owner="alice"):
    response = c.post(
        "/api/goals",
        headers=headers(title.encode().hex(), owner),
        json={
            "revision": 0,
            "title": title,
            "weekly_budget_minutes": budget,
            "priority": 2,
            "load_category": "study",
            "allowed_adjustment": "ask",
            "paused": paused,
            "subtasks": [
                {
                    "title": "保留完成",
                    "status": "completed" if completed else "open",
                    "estimated_minutes": 30,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_shared_six_hour_upper_bound_has_one_ten_hour_budget_and_keeps_unknown_spent(
    tmp_path,
):
    with linked_client(tmp_path) as c:
        seed(
            c,
            settings(),
            (
                "busy",
                "fixed_event",
                {
                    "starts_at": "2026-11-02T09:00:00+08:00",
                    "ends_at": "2026-11-02T10:00:00+08:00",
                },
                "alice",
            ),
        )
        first = goal(c, "英语", 300)
        second = goal(c, "数学", 300)
        paused = goal(c, "暂停", 500, paused=True, completed=True)
        goal(c, "其他用户", 1000, owner="bob")
        before = resources(c)
        response = c.get("/api/goal-capacity?week_start=2026-11-02", headers=headers())
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "known"
        assert (result["week_start"], result["week_end"], result["timezone"]) == (
            "2026-11-02",
            "2026-11-09",
            "Asia/Shanghai",
        )
        assert result["shared_capacity_upper_bound_minutes"] == 360
        assert result["active_weekly_budget_minutes"] == 600
        assert result["minimum_deficit_minutes"] == 240
        assert result["active_goal_ids"] == [first["id"], second["id"]]
        assert result["paused_goal_ids"] == [paused["id"]]
        assert result["actual_minutes"] is None
        assert result["capacity"]["capacity_upper_bound_minutes"] == 360
        assert resources(c) == before  # no tasks, plans or settings changes on read
        assert (
            len(
                c.get("/api/goals", headers=headers()).json()["goals"][2]["data"][
                    "completion_history"
                ]
            )
            == 1
        )


def test_capacity_pause_versions_owner_and_future_complete_week_are_checked(tmp_path):
    with linked_client(tmp_path) as c:
        seed(c, settings())
        a = goal(c, "暂停切换", 600, completed=True)
        first = c.get("/api/goal-capacity", headers=headers())
        assert first.status_code == 200, first.text
        assert first.json()["week_start"] == "2026-11-02"
        paused = c.patch(
            f"/api/goals/{a['id']}",
            headers=headers("pause"),
            json={"revision": a["revision"], "paused": True},
        )
        assert paused.status_code == 200
        stale = c.get(
            f"/api/goal-capacity?expected_source_revision={first.json()['source_revision']}",
            headers=headers(),
        )
        assert stale.status_code == 409
        current = c.get("/api/goal-capacity", headers=headers()).json()
        assert (
            current["active_weekly_budget_minutes"]
            == current["minimum_deficit_minutes"]
            == 0
        )
        assert len(paused.json()["data"]["completion_history"]) == 1
        assert (
            c.get(
                "/api/goal-capacity?week_start=2026-10-26", headers=headers()
            ).status_code
            == 422
        )
        assert (
            c.get(
                "/api/goal-capacity?week_start=2026-11-03", headers=headers()
            ).status_code
            == 422
        )
        assert (
            c.get("/api/goal-capacity?timezone=UTC", headers=headers()).status_code
            == 422
        )
        assert c.get("/api/goal-capacity").status_code == 401
        unknown = c.get("/api/goal-capacity", headers=headers(owner="bob")).json()
        assert unknown["status"] == "unknown"
        assert unknown["shared_capacity_upper_bound_minutes"] is None
        assert unknown["actual_minutes"] is None
        assert resources(c, owner="bob") == []
