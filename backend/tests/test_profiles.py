"""Profile contract against a real request transaction and isolated SQLite file."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, Receipt, Resource


def profile_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/profile.db")
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
            except Exception:
                await db.rollback()
                raise

    async def current_user(x_test_owner: str | None = Header(default=None)):
        if not x_test_owner:
            raise HTTPException(401, "login required")
        return SimpleNamespace(id=x_test_owner)

    from app.profile_routes import profile_router

    app.include_router(profile_router(db_session, current_user))
    return TestClient(app)


def headers(key="write", owner="alice"):
    return {"X-Test-Owner": owner, "Idempotency-Key": key}


def body(revision=0, **changes):
    data = {
        "timezone": "Asia/Shanghai",
        "effective_from": "2026-10-01",
        "effective_until": "2026-12-31",
        "preferences": {
            "preferred_study_windows": [
                {
                    "weekdays": [1, 2, 3, 4, 5],
                    "start": "19:00",
                    "end": "21:00",
                    "task_type": "deep",
                }
            ],
            "energy_windows": [
                {
                    "weekdays": [1, 2, 3, 4, 5],
                    "start": "19:00",
                    "end": "21:00",
                    "level": "high",
                }
            ],
            "focus_minutes": 45,
            "break_minutes": 10,
            "review_interval_days": 3,
            "daily_load_minutes": 120,
            "leisure_protection": "prefer_protect",
        },
    }
    data.update(changes)
    return {"revision": revision, "data": data}


def resources(c, kind=None):
    async def read():
        async with c.app.state.sessions() as db:
            query = select(Resource)
            if kind:
                query = query.where(Resource.kind == kind)
            return list((await db.scalars(query)).all())

    return c.portal.call(read)


def test_read_absent_is_unknown_and_has_no_writes(tmp_path):
    with profile_client(tmp_path) as c:
        assert c.get("/api/profile").status_code == 401
        response = c.get("/api/profile", headers=headers())
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["id"] is None
        assert result["revision"] == 0
        assert result["source_revision"] == 0
        assert result["contract_version"] == "profile-v1"
        assert result["data"]["source"] == "unknown"
        assert result["data"]["confirmed"] is False
        assert result["data"]["sample_count"] == 0
        assert result["data"]["timezone"] is None
        assert all(v is None for v in result["data"]["preferences"].values())
        assert result["suggestions"] == []
        assert resources(c) == []


def test_explicit_save_and_retry_change_revision_and_event_once(tmp_path):
    with profile_client(tmp_path) as c:
        request = body()
        first = c.put("/api/profile", json=request, headers=headers())
        assert first.status_code == 200, first.text
        saved = first.json()
        assert saved["data"]["source"] == "user"
        assert saved["data"]["confirmed"] is True
        assert saved["data"]["sample_count"] == 0
        assert saved["data"]["preferences"]["focus_minutes"] == 45
        assert (
            saved["data"]["preferences"]["preferred_study_windows"][0]["task_type"]
            == "deep"
        )
        assert saved["revision"] == 1
        assert saved["source_revision"] == 2
        assert c.put("/api/profile", json=request, headers=headers()).json() == saved
        assert len(resources(c, "user_profile")) == 1
        events = resources(c, "planning_event")
        assert len(events) == 1
        assert events[0].data["event_type"] == "profile_changed"
        assert events[0].data["details"]["source_revision"] == 2
        assert c.get("/api/profile", headers=headers()).json() == saved
        changed = body(1, preferences={"focus_minutes": 30})
        assert c.put("/api/profile", json=changed, headers=headers()).status_code == 409
        second = c.put("/api/profile", json=changed, headers=headers("second")).json()
        assert second["revision"] == 2
        assert second["source_revision"] == 3
        assert second["data"]["preferences"]["daily_load_minutes"] is None
        assert (
            c.put("/api/profile", json=changed, headers=headers("stale")).status_code
            == 409
        )


def test_owner_isolation_and_reset_preserves_tasks_and_courses(tmp_path):
    with profile_client(tmp_path) as c:
        first = c.put("/api/profile", json=body(), headers=headers()).json()

        async def seed():
            async with c.app.state.sessions() as db:
                db.add_all(
                    [
                        Resource(
                            id="task",
                            owner_id="alice",
                            kind="task",
                            data={"title": "keep"},
                        ),
                        Resource(
                            id="course",
                            owner_id="alice",
                            kind="course",
                            data={"name": "keep"},
                        ),
                    ]
                )
                await db.commit()

        c.portal.call(seed)
        bob = c.get("/api/profile", headers=headers(owner="bob")).json()
        assert bob["revision"] == 0
        assert (
            c.post(
                "/api/profile/reset",
                json={"revision": first["revision"]},
                headers=headers("reset", "bob"),
            ).status_code
            == 409
        )
        reset = c.post(
            "/api/profile/reset",
            json={"revision": first["revision"]},
            headers=headers("reset"),
        )
        assert reset.status_code == 200, reset.text
        cleared = reset.json()
        assert cleared["revision"] == 2
        assert cleared["data"]["source"] == "user"
        assert cleared["data"]["confirmed"] is True
        assert all(v is None for v in cleared["data"]["preferences"].values())
        assert (
            c.post(
                "/api/profile/reset", json={"revision": 1}, headers=headers("reset")
            ).json()
            == cleared
        )
        assert (
            c.post(
                "/api/profile/reset",
                json={"revision": 1},
                headers=headers("stale-reset"),
            ).status_code
            == 409
        )
        assert [r.data for r in resources(c, "task")] == [{"title": "keep"}]
        assert [r.data for r in resources(c, "course")] == [{"name": "keep"}]
        assert len(resources(c, "planning_event")) == 2
        saved_bob = c.put(
            "/api/profile", json=body(), headers=headers(owner="bob")
        ).json()
        assert saved_bob["id"] != first["id"]
        assert c.get("/api/profile", headers=headers()).json() == cleared


@pytest.mark.parametrize(
    "changes",
    [
        {"timezone": "Not/AZone"},
        {"timezone": "../etc/passwd"},
        {"effective_until": "2026-09-01"},
        {"preferences": {"focus_minutes": 0}},
        {"preferences": {"focus_minutes": 241}},
        {"preferences": {"break_minutes": -1}},
        {"preferences": {"break_minutes": 121}},
        {"preferences": {"review_interval_days": 0}},
        {"preferences": {"review_interval_days": 366}},
        {"preferences": {"daily_load_minutes": 721}},
        {"preferences": {"daily_load_minutes": True}},
        {"preferences": {"focus_minutes": "45"}},
        {"preferences": {"leisure_protection": "hard"}},
        {
            "preferences": {
                "energy_windows": [
                    {"weekdays": [1], "start": "21:00", "end": "19:00", "level": "high"}
                ]
            }
        },
        {
            "preferences": {
                "preferred_study_windows": [
                    {"weekdays": [0], "start": "19:00", "end": "21:00"}
                ]
            }
        },
        {
            "preferences": {
                "preferred_study_windows": [
                    {"weekdays": [1], "start": "19:00+08:00", "end": "21:00+08:00"}
                ]
            }
        },
        {
            "preferences": {
                "energy_windows": [
                    {
                        "weekdays": [1],
                        "start": "19:00",
                        "end": "21:00",
                        "level": "high",
                    },
                    {"weekdays": [1], "start": "20:00", "end": "22:00", "level": "low"},
                ]
            }
        },
        {"source": "system"},
        {"confirmed": False},
        {"sample_count": 99},
        {"preferences": {"sleep_start": "23:00"}},
    ],
)
def test_invalid_preferences_are_rejected_without_effects(tmp_path, changes):
    with profile_client(tmp_path) as c:
        response = c.put("/api/profile", json=body(**changes), headers=headers())
        assert response.status_code == 422, response.text
        assert resources(c) == []


def test_null_zero_and_empty_are_distinct_and_no_key_is_rejected(tmp_path):
    with profile_client(tmp_path) as c:
        request = body(
            preferences={
                "daily_load_minutes": 0,
                "break_minutes": 0,
                "preferred_study_windows": [],
            }
        )
        assert (
            c.put(
                "/api/profile", json=request, headers={"X-Test-Owner": "alice"}
            ).status_code
            == 422
        )
        response = c.put("/api/profile", json=request, headers=headers())
        assert response.status_code == 200, response.text
        preferences = response.json()["data"]["preferences"]
        assert preferences["daily_load_minutes"] == 0
        assert preferences["break_minutes"] == 0
        assert preferences["preferred_study_windows"] == []
        assert preferences["energy_windows"] is None


def test_profile_event_and_receipt_rollback_with_global_revision(tmp_path, monkeypatch):
    from app import profiles

    with profile_client(tmp_path) as c:
        before = c.put("/api/profile", json=body(), headers=headers()).json()

        async def fail(*args, **kwargs):
            raise RuntimeError("synthetic profile event failure")

        monkeypatch.setattr(profiles, "record_change", fail)
        with pytest.raises(RuntimeError, match="synthetic profile event"):
            c.put(
                "/api/profile",
                json=body(1, preferences={"focus_minutes": 30}),
                headers=headers("failed"),
            )
        assert c.get("/api/profile", headers=headers()).json() == before
        assert len(resources(c, "planning_event")) == 1

        async def receipt_count():
            async with c.app.state.sessions() as db:
                return len(list((await db.scalars(select(Receipt))).all()))

        assert c.portal.call(receipt_count) == 1
