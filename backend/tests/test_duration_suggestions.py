"""Duration consumption only: real SQLite, typed seeded producer resources."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.contracts import StudentSettings
from app.db import Base, Receipt, Resource


def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/duration.db")
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

    async def user(x_test_owner: str | None = Header(default=None)):
        if not x_test_owner:
            raise HTTPException(401)
        return SimpleNamespace(id=x_test_owner)

    from app.duration_suggestions_routes import duration_suggestions_router

    app.include_router(duration_suggestions_router(db_session, user))
    return TestClient(app)


def headers(key="action", owner="alice"):
    return {"X-Test-Owner": owner, "Idempotency-Key": key}


def db_call(c, fn):
    async def run():
        async with c.app.state.sessions() as db:
            result = await fn(db)
            await db.commit()
            return result

    return c.portal.call(run)


def resources(c, kind=None, model=Resource):
    async def read(db):
        q = select(model)
        if kind:
            q = q.where(Resource.kind == kind)
        return list((await db.scalars(q)).all())

    return db_call(c, read)


def seed(c, **overrides):
    async def write(db):
        db.add(
            Resource(
                id="settings",
                owner_id="alice",
                kind="settings",
                data=StudentSettings().model_dump(mode="json"),
            )
        )
        db.add(
            Resource(
                id="task",
                owner_id="alice",
                kind="task",
                data={"title": "作业", "status": "open"},
            )
        )
        db.add(
            Resource(
                id="step",
                owner_id="alice",
                kind="step",
                data={
                    "task_id": "task",
                    "title": "阅读",
                    "status": "open",
                    "estimated_minutes": 30,
                    "spent_minutes": 0,
                },
            )
        )
        db.add(
            Resource(
                id="untouched",
                owner_id="alice",
                kind="step",
                data={"task_id": "task", "title": "其他步骤", "estimated_minutes": 20},
            )
        )
        db.add(
            Resource(
                id="record",
                owner_id="alice",
                kind="execution",
                data={
                    "task_id": "task",
                    "step_id": "step",
                    "actual_minutes": 45,
                    "feedback": "completed",
                },
            )
        )
        data = {
            "schema_version": 1,
            "source": "duration_generator",
            "task_id": "task",
            "task_revision": 1,
            "step_id": "step",
            "step_revision": 1,
            "source_revision": 1,
            "default_estimated_minutes": 30,
            "suggested_minutes": 45,
            "reasons": ["已确认执行样本比原预计更长"],
            "sample_basis": [
                {
                    "execution_id": "record",
                    "execution_revision": 1,
                    "actual_minutes": 45,
                    "feedback": "completed",
                }
            ],
            "state": "pending",
            "applied_step_revision": None,
            "applied_source_revision": None,
        }
        data.update(overrides)
        db.add(
            Resource(
                id="suggestion", owner_id="alice", kind="duration_suggestion", data=data
            )
        )

    db_call(c, write)


def action(
    c,
    kind="accept",
    key="action",
    revision=1,
    step_revision=1,
    source_revision=1,
    owner="alice",
    **extra,
):
    return c.post(
        "/api/duration-suggestions/suggestion/actions",
        headers=headers(key, owner),
        json={
            "revision": revision,
            "task_revision": 1,
            "step_revision": step_revision,
            "source_revision": source_revision,
            "action": kind,
            **extra,
        },
    )


def test_absent_generator_is_readonly_honest_and_authenticated(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/api/duration-suggestions").status_code == 401
        data = c.get("/api/duration-suggestions", headers=headers()).json()
        assert (
            data["generation_status"] == "ready" and data["suggestions"] == []
        )
        assert data["source_revision"] == 0 and resources(c) == []


def test_typed_reasons_samples_accept_only_target_step_and_receipt_retry(tmp_path):
    with client(tmp_path) as c:
        seed(c)
        listed = c.get("/api/duration-suggestions", headers=headers()).json()
        item = listed["suggestions"][0]
        assert item["freshness"] == "fresh" and item["data"]["reasons"] == [
            "已确认执行样本比原预计更长"
        ]
        assert item["data"]["sample_basis"][0]["actual_minutes"] == 45
        before = {r.id: (r.revision, r.data) for r in resources(c)}
        result = action(c)
        assert result.status_code == 200, result.text
        out = result.json()
        assert out["step"]["data"]["estimated_minutes"] == 45
        assert (
            out["step"]["revision"] == 2
            and out["suggestion"]["data"]["state"] == "accepted"
        )
        assert out["suggestion"]["data"]["applied_source_revision"] == 2
        assert action(c).json() == out
        assert action(c, "reject").status_code == 409
        after = {r.id: (r.revision, r.data) for r in resources(c)}
        assert (
            after["task"] == before["task"]
            and after["record"] == before["record"]
            and after["untouched"] == before["untouched"]
        )
        assert (
            len(resources(c, "planning_event")) == len(resources(c, model=Receipt)) == 1
        )

        async def unrelated(db):
            r = await db.get(Resource, "settings")
            r.revision += 1

        db_call(c, unrelated)
        assert action(c).json() == out
        assert action(c, key="stale-new").status_code == 409
    with client(tmp_path) as c:
        assert action(c).json() == out
        assert (
            c.get("/api/duration-suggestions", headers=headers()).json()["suggestions"][
                0
            ]["freshness"]
            == "stale"
        )


def test_reject_changes_no_estimates_and_restore_default_is_explicit(tmp_path):
    with client(tmp_path) as c:
        seed(c)
        assert action(c, "restore_default").status_code == 409
        accepted = action(c).json()
        assert accepted["suggestion"]["data"]["state"] == "accepted"
        restored = action(
            c,
            "restore_default",
            "restore",
            revision=2,
            step_revision=2,
            source_revision=2,
        )
        assert restored.status_code == 200, restored.text
        out = restored.json()
        assert out["step"]["data"]["estimated_minutes"] == 30
        assert (
            out["step"]["revision"] == 3
            and out["suggestion"]["data"]["state"] == "restored"
        )
        assert (
            action(
                c,
                "restore_default",
                "restore",
                revision=2,
                step_revision=2,
                source_revision=2,
            ).json()
            == out
        )
        assert len(resources(c, "planning_event")) == 2
    other = tmp_path / "other"
    other.mkdir()
    with client(other) as c:
        seed(c)
        rejected = action(c, "reject")
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["suggestion"]["data"]["state"] == "rejected"
        assert rejected.json()["step"]["data"]["estimated_minutes"] == 30
        assert rejected.json()["step"]["revision"] == 1
        assert resources(c, "settings")[0].revision == 1


@pytest.mark.parametrize(
    "target,patch",
    [
        ("settings", {}),
        ("task", {"title": "新标题"}),
        ("step", {"estimated_minutes": 35}),
        ("record", {"actual_minutes": 50}),
        ("step", {"task_id": "someone-else"}),
        ("step", {"status": "completed"}),
    ],
)
def test_stale_sources_or_wrong_target_reject_without_effects(tmp_path, target, patch):
    with client(tmp_path) as c:
        seed(c)

        async def change(db):
            r = await db.get(Resource, target)
            r.data = {**r.data, **patch}
            r.revision += 1

        db_call(c, change)
        listed = c.get("/api/duration-suggestions", headers=headers()).json()
        assert listed["suggestions"][0]["freshness"] == "stale"
        assert action(c).status_code == 409
        assert (
            resources(c, model=Receipt) == [] and resources(c, "planning_event") == []
        )


def test_owner_contract_validation_and_sample_facts_are_not_invented(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            sample_basis=[
                {
                    "execution_id": "record",
                    "execution_revision": 1,
                    "actual_minutes": 999,
                    "feedback": "completed",
                }
            ],
        )
        assert action(c, owner="bob").status_code == 404
        assert (
            c.get("/api/duration-suggestions", headers=headers(owner="bob")).json()[
                "suggestions"
            ]
            == []
        )
        assert action(c).status_code == 409
        for bad in (
            {"revision": True},
            {"step_revision": "1"},
            {"action": "auto"},
            {"suggested_minutes": 90},
        ):
            assert action(c, **bad).status_code == 422

        async def corrupt(db):
            r = await db.get(Resource, "suggestion")
            r.data = {**r.data, "suggested_minutes": False}

        db_call(c, corrupt)
        listed = c.get("/api/duration-suggestions", headers=headers()).json()
        assert listed["suggestions"] == [] and listed["invalid_suggestion_count"] == 1
        assert action(c).status_code == 409


def test_restore_does_not_overwrite_manual_edit_and_rollback_is_atomic(
    tmp_path, monkeypatch
):
    from app import duration_suggestions

    with client(tmp_path) as c:
        seed(c)

        async def fail(*args, **kwargs):
            raise RuntimeError("duration event failure")

        original = duration_suggestions.record_change
        monkeypatch.setattr(duration_suggestions, "record_change", fail)
        with pytest.raises(RuntimeError, match="duration event failure"):
            action(c)
        assert resources(c, "step")[0].data["estimated_minutes"] == 30
        assert resources(c, "settings")[0].revision == 1
        assert resources(c, model=Receipt) == []
        assert resources(c, "duration_suggestion")[0].revision == 1
        monkeypatch.setattr(duration_suggestions, "record_change", original)
        assert action(c).status_code == 200

        async def manual(db):
            r = await db.get(Resource, "step")
            r.data = {**r.data, "estimated_minutes": 55}
            r.revision += 1

        db_call(c, manual)
        assert (
            action(
                c,
                "restore_default",
                "restore",
                revision=2,
                step_revision=3,
                source_revision=2,
            ).status_code
            == 409
        )
        assert (
            next(r for r in resources(c, "step") if r.id == "step").data[
                "estimated_minutes"
            ]
            == 55
        )


def test_unknown_default_restores_unknown_without_touching_actual_facts(tmp_path):
    with client(tmp_path) as c:
        seed(c, default_estimated_minutes=None)

        async def unknown(db):
            step = await db.get(Resource, "step")
            step.data = {**step.data, "estimated_minutes": None}

        db_call(c, unknown)
        assert action(c).status_code == 200
        restored = action(
            c,
            "restore_default",
            "restore",
            revision=2,
            step_revision=2,
            source_revision=2,
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["step"]["data"]["estimated_minutes"] is None
        assert restored.json()["step"]["data"]["spent_minutes"] == 0
        assert resources(c, "execution")[0].data["actual_minutes"] == 45


def test_superseded_sample_wrong_owned_target_and_wrong_baseline_cannot_apply(tmp_path):
    with client(tmp_path) as c:
        seed(c)

        async def correct(db):
            db.add(
                Resource(
                    id="correction",
                    owner_id="alice",
                    kind="execution",
                    data={
                        "task_id": "task",
                        "step_id": "step",
                        "actual_minutes": 50,
                        "feedback": "completed",
                        "supersedes_id": "record",
                    },
                )
            )

        db_call(c, correct)
        assert action(c).status_code == 409

        async def other_owner(db):
            record = await db.get(Resource, "correction")
            await db.delete(record)
            step = await db.get(Resource, "step")
            step.owner_id = "bob"

        db_call(c, other_owner)
        assert action(c).status_code == 409
        item = c.get("/api/duration-suggestions", headers=headers()).json()[
            "suggestions"
        ][0]
        assert item["step_title"] is None
    other = tmp_path / "baseline"
    other.mkdir()
    with client(other) as c:
        seed(c, default_estimated_minutes=25)
        assert action(c).status_code == 409
        assert resources(c, model=Receipt) == []
