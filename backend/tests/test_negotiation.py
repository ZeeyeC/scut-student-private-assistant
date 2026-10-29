"""Negotiation uses real A planning and isolated SQLite, never a model stub."""

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.contracts import StudentSettings
from app.db import Base, Resource


def client(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}/negotiation.db")
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

    async def owner(x_test_owner: str = Header(default="alice")):
        return SimpleNamespace(id=x_test_owner)

    from app.negotiation_routes import negotiation_router

    app.include_router(negotiation_router(db_session, owner))
    return TestClient(app)


@pytest.fixture
def c(tmp_path, monkeypatch):
    from app import planner

    monkeypatch.setattr(
        planner, "now", lambda: datetime.fromisoformat("2030-12-30T08:00:00+08:00")
    )
    with client(tmp_path) as c:

        async def seed():
            async with c.app.state.sessions() as db:
                settings = StudentSettings(
                    study_windows=[{"start": "09:00", "end": "12:00"}],
                    daily_limit_minutes=120,
                    buffer_minutes=0,
                )
                db.add_all(
                    [
                        Resource(
                            id="settings",
                            owner_id="alice",
                            kind="settings",
                            data=settings.model_dump(mode="json"),
                        ),
                        Resource(
                            id="task",
                            owner_id="alice",
                            kind="task",
                            data={
                                "title": "复习",
                                "status": "open",
                                "priority": 2,
                                "due_at": "2030-12-30T18:00:00+08:00",
                            },
                        ),
                        Resource(
                            id="step",
                            owner_id="alice",
                            kind="step",
                            data={
                                "task_id": "task",
                                "title": "练习",
                                "status": "open",
                                "estimated_minutes": 60,
                                "spent_minutes": 0,
                                "dependency_ids": [],
                            },
                        ),
                    ]
                )
                await db.commit()

        c.portal.call(seed)
        yield c


def rows(c, kind):
    async def read():
        async with c.app.state.sessions() as db:
            return [
                dict(id=r.id, revision=r.revision, data=r.data)
                for r in await db.scalars(select(Resource).where(Resource.kind == kind))
            ]

    return c.portal.call(read)


def send(c, path, body, key="operation", method="POST", owner="alice"):
    return c.request(
        method,
        "/api/planning-intents" + path,
        json=body,
        headers={"Idempotency-Key": key, "X-Test-Owner": owner},
    )


def intent_data(**overrides):
    return {
        "description": "周一保住复习，尽量晚一点开始",
        "target_date": "2030-12-30",
        "horizon_days": 1,
        "timezone": "Asia/Shanghai",
        "preferred_intervals": [
            {
                "starts_at": "2030-12-30T11:00:00+08:00",
                "ends_at": "2030-12-30T12:00:00+08:00",
            }
        ],
        **overrides,
    }


def create(c, **changes):
    r = send(c, "", {"source_revision": 1, "data": intent_data(**changes)})
    assert r.status_code == 200, r.text
    return r.json()


def preview(c, intent, key="preview"):
    r = send(
        c,
        f"/{intent['id']}/preview",
        {"revision": intent["revision"], "source_revision": 1},
        key,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_two_real_options_no_formal_writes_choose_replays_and_confirms(c):
    i = preview(c, create(c))
    p = i["data"]["preview"]
    assert len(p["options"]) == 2
    assert (
        p["options"][0]["blocks"][0]["starts_at"]
        != p["options"][1]["blocks"][0]["starts_at"]
    )
    assert (
        rows(c, "plan_block")
        == rows(c, "draft")
        == rows(c, "scheduling_constraint")
        == []
    )
    body = {
        "revision": i["revision"],
        "source_revision": 1,
        "option_id": p["options"][1]["id"],
    }
    chosen = send(c, f"/{i['id']}/choose", body, "choose")
    assert chosen.status_code == 200, chosen.text
    draft = chosen.json()["draft"]
    assert len(rows(c, "draft")) == 1 and rows(c, "plan_block") == []
    assert draft["data"]["source"]["planning_inputs"]["constraints"]

    # Original confirmation's generated hash, source guard, and save_plan are used.
    async def confirm():
        from app.imports import commit_draft

        async with c.app.state.sessions() as db:
            await commit_draft(db, "alice", draft["id"], draft["revision"])
            await db.commit()

    c.portal.call(confirm)
    assert len(rows(c, "plan_block")) == 1
    assert send(c, f"/{i['id']}/choose", body, "choose").json() == chosen.json()
    assert send(c, f"/{i['id']}/choose", body, "new-key").status_code == 409


def test_identical_allocations_deduplicate_and_modify_same_intent(c):
    i = preview(c, create(c, preferred_intervals=[]))
    assert len(i["data"]["preview"]["options"]) == 1
    assert "一种" in i["data"]["preview"]["explanation"]
    r = send(
        c,
        f"/{i['id']}",
        {
            "revision": i["revision"],
            "source_revision": 1,
            "data": intent_data(reduced_daily_limit_minutes=30),
        },
        "edit",
        "PATCH",
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == i["id"] and r.json()["data"]["preview"] is None
    assert len(rows(c, "planning_intent")) == 1


def test_no_solution_does_not_invent_window(c):
    i = preview(
        c,
        create(
            c,
            protected_intervals=[
                {
                    "starts_at": "2030-12-30T09:00:00+08:00",
                    "ends_at": "2030-12-30T12:00:00+08:00",
                }
            ],
        ),
    )
    assert i["data"]["preview"]["options"] == []
    assert i["data"]["preview"]["conflicts"]
    assert "修改" in i["data"]["preview"]["explanation"]
    assert rows(c, "scheduling_constraint") == []


@pytest.mark.parametrize(
    "changes",
    [
        {
            "preferred_intervals": [
                {
                    "starts_at": "2030-12-30T12:00:00+08:00",
                    "ends_at": "2030-12-30T11:00:00+08:00",
                }
            ]
        },
        {"timezone": "unknown"},
        {"target_date": None},
        {
            "protected_intervals": [
                {
                    "starts_at": "2030-12-29T09:00:00+08:00",
                    "ends_at": "2030-12-30T10:00:00+08:00",
                }
            ]
        },
    ],
)
def test_invalid_explicit_conditions_rejected(c, changes):
    assert (
        send(c, "", {"source_revision": 1, "data": intent_data(**changes)}).status_code
        == 422
    )


def test_source_owner_keep_refs_and_limit(c):
    assert (
        send(c, "", {"source_revision": 99, "data": intent_data()}).status_code == 409
    )
    assert (
        send(
            c,
            "",
            {"source_revision": 1, "data": intent_data(keep_block_ids=["missing"])},
        ).status_code
        == 404
    )
    assert (
        send(
            c,
            "",
            {
                "source_revision": 1,
                "data": intent_data(reduced_daily_limit_minutes=180),
            },
        ).status_code
        == 422
    )
    i = create(c)
    assert (
        send(
            c, f"/{i['id']}/preview", {"revision": 1, "source_revision": 1}, owner="bob"
        ).status_code
        == 404
    )
    assert c.get("/api/planning-intents", headers={"X-Test-Owner": "bob"}).json() == []


def test_cancel_and_restart_reconstruct_intent(c, tmp_path):
    i = preview(c, create(c))
    r = send(
        c,
        f"/{i['id']}/cancel",
        {"revision": i["revision"], "source_revision": 1},
        "cancel",
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "cancelled"
    with client(tmp_path) as restarted:
        restored = restarted.get("/api/planning-intents").json()
        assert restored[0] == r.json()
    assert rows(c, "plan_block") == rows(c, "scheduling_constraint") == []


def add_block(
    c, *, bid="keep", owner="alice", locked=False, day="2030-12-30", timer=False
):
    async def seed():
        async with c.app.state.sessions() as db:
            db.add(
                Resource(
                    id=bid,
                    owner_id=owner,
                    kind="plan_block",
                    data={
                        "task_id": "task",
                        "step_id": "step",
                        "title": "保留复习",
                        "starts_at": f"{day}T10:00:00+08:00",
                        "ends_at": f"{day}T11:00:00+08:00",
                        "status": "suggested",
                        "locked": locked,
                    },
                )
            )
            if timer:
                db.add(
                    Resource(
                        id="timer",
                        owner_id=owner,
                        kind="execution_timer",
                        data={"status": "running", "target": {"plan_block_id": bid}},
                    )
                )
            await db.commit()

    c.portal.call(seed)


@pytest.mark.parametrize("kind", ["keep", "locked", "timer"])
def test_kept_locked_and_active_timer_blocks_survive_original_confirmation(c, kind):
    add_block(c, locked=kind == "locked", timer=kind == "timer")
    original = rows(c, "plan_block")
    i = preview(c, create(c, keep_block_ids=["keep"] if kind == "keep" else []))
    assert len(i["data"]["preview"]["options"]) == 1
    option = i["data"]["preview"]["options"][0]
    assert option["changes"]["retained_ids"] == ["keep"]
    r = send(
        c,
        f"/{i['id']}/choose",
        {"revision": i["revision"], "source_revision": 1, "option_id": option["id"]},
        "choice",
    )
    assert r.status_code == 200, r.text
    d = r.json()["draft"]

    async def confirm():
        from app.imports import commit_draft

        async with c.app.state.sessions() as db:
            await commit_draft(db, "alice", d["id"], d["revision"])
            await db.commit()

    c.portal.call(confirm)
    assert rows(c, "plan_block") == original
    current = c.get("/api/planning-intents").json()[0]
    # Cancel after confirmation never reverses the confirmed plan.
    version = rows(c, "settings")[0]["revision"]
    assert (
        send(
            c,
            f"/{i['id']}/cancel",
            {"revision": current["revision"], "source_revision": version},
            "cancel-confirmed",
        ).status_code
        == 200
    )
    assert rows(c, "plan_block") == original


def test_temporary_hard_conflict_cannot_remove_keep_or_locked(c):
    add_block(c, locked=True)
    i = preview(
        c,
        create(
            c,
            protected_intervals=[
                {
                    "starts_at": "2030-12-30T10:00:00+08:00",
                    "ends_at": "2030-12-30T11:00:00+08:00",
                }
            ],
        ),
    )
    assert i["data"]["preview"]["options"] == []
    assert any("冲突" in x for x in i["data"]["preview"]["conflicts"])
    assert len(rows(c, "plan_block")) == 1


def test_confirmed_hard_constraints_and_cross_year(c):
    async def seed():
        from app.contracts import SchedulingConstraint

        async with c.app.state.sessions() as db:
            constraint = SchedulingConstraint(
                timezone="Asia/Shanghai",
                starts_at="2030-12-30T09:00:00+08:00",
                ends_at="2030-12-30T11:00:00+08:00",
            )
            db.add(
                Resource(
                    id="hard",
                    owner_id="alice",
                    kind="scheduling_constraint",
                    data={
                        **constraint.model_dump(mode="json"),
                        "active": True,
                        "confirmed": True,
                    },
                )
            )
            await db.commit()

    c.portal.call(seed)
    original = rows(c, "scheduling_constraint")
    i = preview(c, create(c, horizon_days=7))
    assert len(i["data"]["preview"]["options"]) == 1
    assert datetime.fromisoformat(
        i["data"]["preview"]["options"][0]["blocks"][0]["starts_at"]
    ) == datetime.fromisoformat("2030-12-30T11:00:00+08:00")
    assert rows(c, "scheduling_constraint") == original


def test_foreign_out_of_range_keep_and_stale_preview(c):
    add_block(c, bid="foreign", owner="bob")
    add_block(c, bid="outside", day="2030-12-31")
    assert (
        send(
            c,
            "",
            {"source_revision": 1, "data": intent_data(keep_block_ids=["foreign"])},
        ).status_code
        == 404
    )
    assert (
        send(
            c,
            "",
            {"source_revision": 1, "data": intent_data(keep_block_ids=["outside"])},
        ).status_code
        == 422
    )
    i = preview(c, create(c))

    async def change():
        async with c.app.state.sessions() as db:
            r = await db.get(Resource, "settings")
            r.revision += 1
            await db.commit()

    c.portal.call(change)
    choose = {"revision": i["revision"], "source_revision": 1, "option_id": "earliest"}
    assert send(c, f"/{i['id']}/choose", choose, "stale").status_code == 409
    assert (
        send(
            c, f"/{i['id']}/choose", {**choose, "source_revision": 2}, "new-version"
        ).status_code
        == 409
    )
    fresh = send(
        c,
        f"/{i['id']}/preview",
        {"revision": i["revision"], "source_revision": 2},
        "fresh-preview",
    )
    assert fresh.status_code == 200, fresh.text


def test_cancel_chosen_pending_draft_invalidates_only_own_candidate(c):
    i = preview(c, create(c))
    r = send(
        c,
        f"/{i['id']}/choose",
        {"revision": i["revision"], "source_revision": 1, "option_id": "earliest"},
        "choose",
    ).json()
    cancel = send(
        c,
        f"/{i['id']}/cancel",
        {"revision": r["intent"]["revision"], "source_revision": 1},
        "cancel",
    )
    assert cancel.status_code == 200
    assert rows(c, "draft")[0]["data"]["status"] == "superseded"
    assert rows(c, "plan_block") == []


def test_no_solution_not_disguised_by_completed_block_outside_range(c):
    async def seed():
        async with c.app.state.sessions() as db:
            db.add(
                Resource(
                    id="past",
                    owner_id="alice",
                    kind="plan_block",
                    data={
                        "task_id": "task",
                        "step_id": "step",
                        "title": "历史安排",
                        "starts_at": "2030-12-29T09:00:00+08:00",
                        "ends_at": "2030-12-29T10:00:00+08:00",
                        "status": "completed",
                        "locked": False,
                    },
                )
            )
            await db.commit()

    c.portal.call(seed)
    i = preview(
        c,
        create(
            c,
            protected_intervals=[
                {
                    "starts_at": "2030-12-30T09:00:00+08:00",
                    "ends_at": "2030-12-30T12:00:00+08:00",
                }
            ],
        ),
    )
    assert i["data"]["preview"]["options"] == []
    assert i["data"]["preview"]["conflicts"]
    assert len(rows(c, "plan_block")) == 1


def test_draft_failure_rolls_back_intent_and_receipt(c, monkeypatch):
    from app import imports
    from app.db import Receipt

    i = preview(c, create(c))
    original = imports.create_draft

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("synthetic save failure")

    monkeypatch.setattr(imports, "create_draft", fail)
    body = {"revision": i["revision"], "source_revision": 1, "option_id": "earliest"}
    with pytest.raises(RuntimeError, match="synthetic save"):
        send(c, f"/{i['id']}/choose", body, "retry-after-rollback")
    assert rows(c, "draft") == []
    assert c.get("/api/planning-intents").json()[0] == i

    async def receipts():
        async with c.app.state.sessions() as db:
            return list(
                await db.scalars(
                    select(Receipt).where(Receipt.key == "retry-after-rollback")
                )
            )

    assert c.portal.call(receipts) == []
    monkeypatch.setattr(imports, "create_draft", original)
    assert (
        send(c, f"/{i['id']}/choose", body, "retry-after-rollback").status_code == 200
    )
