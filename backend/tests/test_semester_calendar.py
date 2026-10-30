"""Batch semester rules use synthetic SQLite only, never a personal database."""

from copy import deepcopy
from datetime import date
from importlib import import_module
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import store
from app.calendar import expand_calendar
from app.db import Base, Resource


def service():
    try:
        return import_module("app.semester_calendar")
    except ImportError as exc:
        pytest.fail(f"semester batch service is not implemented: {exc}")


@pytest.fixture
async def sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/semester.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed(db, tz="Asia/Shanghai", anchor="2026-10-12"):
    s = await store.settings(db, "alice")
    s.data = {
        **s.data,
        "timezone": tz,
        "week1_monday": anchor,
        "week_count": 4,
        "periods": {
            "1": {"start": "09:00", "end": "10:00"},
            "3": {"start": "14:00", "end": "15:00"},
        },
    }
    for cid in ["math", "physics"]:
        db.add(
            Resource(
                id=cid,
                owner_id="alice",
                kind="course",
                data={
                    "source_key": cid,
                    "name": cid,
                    "weekday": 3,
                    "weeks": [1, 2, 3],
                    "periods": [1],
                    "campus": "主校区",
                    "location": "101",
                },
            )
        )
    await db.commit()


def rule(**patch):
    return {
        "operation": "apply",
        "rule_kind": "practice_week",
        "title": "经确认实践周",
        "reason": "教务通知第3条",
        "source_scope": "本学期第1至2周，所选课程停课",
        "course_ids": ["math", "physics"],
        "action": "cancel",
        "start_date": "2026-10-12",
        "end_date": "2026-10-25",
        "mappings": [],
        **patch,
    }


async def draft(db, payload, owner="alice"):
    api = service()
    p = api.validate_semester_payload(payload)
    review = await api.preview_semester(db, owner, p)
    s = await store.settings(db, owner)
    row = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="draft",
        data={
            "draft_kind": "semester_calendar",
            "payload": p,
            "source_revision": s.revision,
            "source": {"preview": review, "generated_hash": store.digest(p)},
            "status": "pending",
        },
    )
    db.add(row)
    await db.flush()
    return row


async def commit(db, row):
    result = await service().save_semester(db, row.owner_id, row, row.data["payload"])
    await store.bump(db, row.owner_id)
    await db.commit()
    return result


async def occurrences(db, start="2026-10-12", end="2026-11-08"):
    s = await store.settings(db, "alice")
    return expand_calendar(
        s.data,
        [store.view(r) for r in await store.rows(db, "alice", "course")],
        [r.data for r in await store.rows(db, "alice", "exception")],
        date.fromisoformat(start),
        date.fromisoformat(end),
    )


async def test_practice_week_all_courses_dates_atomic_and_restart(sessions):
    async with sessions() as db:
        await seed(db)
        d = await draft(db, rule())
        assert len(d.data["source"]["preview"]["changes"]) == 4
        assert len(await occurrences(db)) == 6
        ids = await commit(db, d)
        assert len(ids) == 4
        assert [e["original_date"] for e in await occurrences(db)] == [
            "2026-10-28",
            "2026-10-28",
        ]
        assert len(await store.rows(db, "alice", "planning_event")) == 1
        assert len(await store.rows(db, "alice", "semester_calendar_batch")) == 1
    async with sessions() as db:
        assert len(await occurrences(db)) == 2
        batches = await store.rows(db, "alice", "semester_calendar_batch")
        undo = await draft(
            db,
            {
                "operation": "undo",
                "batch_id": batches[0].id,
                "reason": "撤销实践周通知",
            },
        )
        await commit(db, undo)
        assert len(await occurrences(db)) == 6
        assert not await store.rows(db, "alice", "exception")
        assert len(await store.rows(db, "alice", "planning_event")) == 2


async def test_explicit_makeup_maps_multiple_courses_without_guessing(sessions):
    async with sessions() as db:
        await seed(db)
        d = await draft(
            db,
            rule(
                rule_kind="makeup",
                action="move",
                start_date=None,
                end_date=None,
                mappings=[
                    {"original_date": "2026-10-14", "target_date": "2026-10-18"},
                    {"original_date": "2026-10-21", "target_date": "2026-10-24"},
                ],
            ),
        )
        review = d.data["source"]["preview"]
        assert len(review["changes"]) == 4
        assert review["conflict_report"]["conflict_count"] >= 2
        await commit(db, d)
        events = await occurrences(db)
        assert [e["starts_at"][:10] for e in events] == [
            "2026-10-18",
            "2026-10-18",
            "2026-10-24",
            "2026-10-24",
            "2026-10-28",
            "2026-10-28",
        ]
        assert events[0]["starts_at"].endswith("09:00:00+08:00")
        assert {e["id"] for e in events} == {
            f"{c}:2026-10-{d}" for c in ["math", "physics"] for d in [14, 21, 28]
        }


@pytest.mark.parametrize(
    "patch",
    [
        {"reason": " "},
        {"source_scope": " "},
        {
            "rule_kind": "holiday",
            "action": "move",
            "start_date": None,
            "end_date": None,
            "mappings": [],
        },
        {"course_ids": []},
        {"end_date": "2026-10-01"},
        {"mappings": [{"original_date": "2026-10-14", "target_date": "2026-10-18"}]},
        {
            "action": "move",
            "start_date": None,
            "end_date": None,
            "mappings": [
                {"original_date": "2026-10-14", "target_date": "2026-10-18"},
                {"original_date": "2026-10-14", "target_date": "2026-10-19"},
            ],
        },
    ],
)
async def test_incomplete_or_ambiguous_school_rules_create_no_facts(sessions, patch):
    async with sessions() as db:
        await seed(db)
        with pytest.raises(HTTPException) as error:
            await draft(db, rule(**patch))
        assert error.value.status_code == 422
        assert not await store.rows(db, "alice", "exception")


async def test_owner_hash_and_version_guards(sessions):
    async with sessions() as db:
        await seed(db)
        with pytest.raises(HTTPException) as error:
            await draft(db, rule(), "bob")
        assert error.value.status_code == 404
        d = await draft(db, rule())
        with pytest.raises(HTTPException) as error:
            await service().save_semester(
                db, "alice", d, {**d.data["payload"], "reason": "别的依据"}
            )
        assert error.value.status_code == 422
        await store.bump(db, "alice")
        with pytest.raises(HTTPException) as error:
            await service().save_semester(db, "alice", d, d.data["payload"])
        assert error.value.status_code == 409
        assert not await store.rows(db, "alice", "exception")


async def test_failure_after_writes_rolls_back_entire_batch_and_receipt_retry(
    sessions, monkeypatch
):
    async with sessions() as db:
        await seed(db)
        d = await draft(db, rule())
        await db.commit()
        real = service().record_change

        async def interrupted(*args, **kwargs):
            await real(*args, **kwargs)
            raise HTTPException(503, "synthetic transaction interruption")

        with monkeypatch.context() as patch:
            patch.setattr(service(), "record_change", interrupted)
            with pytest.raises(HTTPException):
                await store.mutate(
                    db,
                    "alice",
                    "semester-confirm",
                    "retry",
                    {"id": d.id},
                    lambda: service().save_semester(db, "alice", d, d.data["payload"]),
                )
        assert not await store.rows(db, "alice", "exception")
        assert not await store.rows(db, "alice", "semester_calendar_batch")
        assert not await store.rows(db, "alice", "planning_event")
        payload = {"id": d.id}
        first = await store.mutate(
            db,
            "alice",
            "semester-confirm",
            "retry",
            payload,
            lambda: service().save_semester(db, "alice", d, d.data["payload"]),
        )
        second = await store.mutate(
            db,
            "alice",
            "semester-confirm",
            "retry",
            payload,
            lambda: service().save_semester(db, "alice", d, d.data["payload"]),
        )
        assert first == second and len(first) == 4
        assert len(await store.rows(db, "alice", "planning_event")) == 1
        with pytest.raises(HTTPException) as error:
            await store.mutate(
                db, "alice", "semester-confirm", "retry", {"id": "other"}, lambda: None
            )
        assert error.value.status_code == 409


async def test_undo_restores_exact_legacy_rows_and_preserves_unrelated_changes(
    sessions,
):
    async with sessions() as db:
        await seed(db)
        old = {
            "course_id": "math",
            "date": "2026-10-14",
            "cancelled": False,
            "starts_at": "2026-10-15T12:00:00+08:00",
            "ends_at": "2026-10-15T13:00:00+08:00",
            "active": True,
            "source": {"kind": "legacy", "reason": "原教师通知"},
        }
        db.add(Resource(id="legacy", owner_id="alice", kind="exception", data=old))
        db.add(
            Resource(
                id="inactive",
                owner_id="alice",
                kind="exception",
                data={**old, "active": False},
            )
        )
        await db.commit()
        d = await draft(db, rule())
        await commit(db, d)
        batch = (await store.rows(db, "alice", "semester_calendar_batch"))[0]
        immutable = deepcopy(batch.data)
        db.add(
            Resource(
                id="unrelated",
                owner_id="alice",
                kind="exception",
                data={**old, "date": "2026-10-28"},
            )
        )
        await store.bump(db, "alice")
        await db.commit()
        u = await draft(
            db,
            {"operation": "undo", "batch_id": batch.id, "reason": "恢复之前的教师通知"},
        )
        await commit(db, u)
        assert (await db.get(Resource, "legacy")).data == old
        assert (await db.get(Resource, "inactive")).data == {**old, "active": False}
        assert await db.get(Resource, "unrelated")
        assert batch.data == immutable
        assert len(await store.rows(db, "alice", "exception")) == 3


async def test_undo_refuses_later_changes_or_new_duplicate_without_partial_restore(
    sessions,
):
    async with sessions() as db:
        await seed(db)
        d = await draft(db, rule())
        await commit(db, d)
        batch = (await store.rows(db, "alice", "semester_calendar_batch"))[0]
        row = (await store.rows(db, "alice", "exception"))[0]
        row.data = {**row.data, "location": "other"}
        row.revision += 1
        await db.commit()
        before = [store.view(r) for r in await store.rows(db, "alice", "exception")]
        with pytest.raises(HTTPException) as error:
            await draft(
                db, {"operation": "undo", "batch_id": batch.id, "reason": "撤销"}
            )
        assert error.value.status_code == 409
        assert [
            store.view(r) for r in await store.rows(db, "alice", "exception")
        ] == before


async def test_date_mapping_keeps_local_clock_and_rejects_dst_gap(sessions):
    async with sessions() as db:
        await seed(db, "America/New_York", "2026-10-26")
        course = await db.get(Resource, "math")
        course.data = {**course.data, "weekday": 7, "weeks": [1]}
        await db.commit()
        payload = rule(
            course_ids=["math"],
            action="move",
            start_date=None,
            end_date=None,
            mappings=[{"original_date": "2026-11-01", "target_date": "2026-11-02"}],
        )
        d = await draft(db, payload)
        assert (
            d.data["source"]["preview"]["changes"][0]["after"]["starts_at"]
            == "2026-11-02T09:00:00-05:00"
        )
        await commit(db, d)
        # An explicit source date with no chosen occurrence must never mean "next class".
        with pytest.raises(HTTPException) as error:
            await draft(
                db,
                {
                    **payload,
                    "mappings": [
                        {"original_date": "2026-11-03", "target_date": "2026-11-04"}
                    ],
                },
            )
        assert error.value.status_code == 422


async def test_outer_confirm_failure_does_not_commit_released_sqlite_savepoint(
    sessions,
):
    async with sessions() as db:
        await seed(db)
        d = await draft(db, rule())
        draft_id = d.id
        await db.commit()
    # A real confirm starts with SELECTs of an already-persisted draft.
    async with sessions() as db:
        d = await db.get(Resource, draft_id)
        await service().save_semester(db, "alice", d, d.data["payload"])
        # Simulate an exception in the remaining receipt/draft/settings work.
        await db.rollback()
    async with sessions() as db:
        assert not await store.rows(db, "alice", "exception")
        assert not await store.rows(db, "alice", "semester_calendar_batch")
        assert not await store.rows(db, "alice", "planning_event")


@pytest.mark.parametrize(
    "anchor,original,target",
    [
        ("2026-03-02", "2026-03-04", "2026-03-08"),
        ("2026-10-26", "2026-10-28", "2026-11-01"),
    ],
)
async def test_dst_missing_or_repeated_target_clock_requires_explicit_single_adjustment(
    sessions, anchor, original, target
):
    async with sessions() as db:
        await seed(db, "America/New_York", anchor)
        s = await store.settings(db, "alice")
        s.data = {
            **s.data,
            "periods": {
                "1": {
                    "start": "01:30" if target.endswith("11-01") else "02:30",
                    "end": "03:30",
                }
            },
        }
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await draft(
                db,
                rule(
                    course_ids=["math"],
                    action="move",
                    start_date=None,
                    end_date=None,
                    mappings=[{"original_date": original, "target_date": target}],
                ),
            )
        assert error.value.status_code == 422
        assert not await store.rows(db, "alice", "exception")


async def test_undo_new_same_occurrence_row_and_stale_course_are_rejected(sessions):
    async with sessions() as db:
        await seed(db)
        d = await draft(db, rule())
        c = await db.get(Resource, "physics")
        c.revision += 1
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await service().save_semester(db, "alice", d, d.data["payload"])
        assert error.value.status_code == 409
        d = await draft(db, rule())
        await commit(db, d)
        batch = (await store.rows(db, "alice", "semester_calendar_batch"))[0]
        db.add(
            Resource(
                id="later-duplicate",
                owner_id="alice",
                kind="exception",
                data={"course_id": "math", "date": "2026-10-14", "cancelled": True},
            )
        )
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await draft(
                db, {"operation": "undo", "batch_id": batch.id, "reason": "撤销"}
            )
        assert error.value.status_code == 409


async def test_mapped_nonconsecutive_periods_keep_real_gap_in_preview_and_saved_calendar(
    sessions,
):
    async with sessions() as db:
        await seed(db)
        c = await db.get(Resource, "math")
        c.data = {**c.data, "periods": [1, 3]}
        await db.commit()
        d = await draft(
            db,
            rule(
                course_ids=["math"],
                action="move",
                start_date=None,
                end_date=None,
                mappings=[{"original_date": "2026-10-14", "target_date": "2026-10-18"}],
            ),
        )
        after = d.data["source"]["preview"]["changes"][0]["after"]
        assert [
            (i["starts_at"][11:16], i["ends_at"][11:16])
            for i in after["occupied_intervals"]
        ] == [("09:00", "10:00"), ("14:00", "15:00")]
        await commit(db, d)
        saved = next(e for e in await occurrences(db) if e["id"] == "math:2026-10-14")
        assert saved == after


async def test_preview_includes_locked_plan_impact_without_mutating_plan(sessions):
    async with sessions() as db:
        await seed(db)
        plan = {
            "title": "已锁定练习",
            "starts_at": "2026-10-18T09:15:00+08:00",
            "ends_at": "2026-10-18T10:15:00+08:00",
            "locked": True,
        }
        db.add(Resource(id="locked", owner_id="alice", kind="plan_block", data=plan))
        await db.commit()
        d = await draft(
            db,
            rule(
                course_ids=["math"],
                action="move",
                start_date=None,
                end_date=None,
                mappings=[{"original_date": "2026-10-14", "target_date": "2026-10-18"}],
            ),
        )
        r = d.data["source"]["preview"]
        assert [p["id"] for p in r["affected_plans"]] == ["locked"]
        assert r["plan_conflicts"][0]["locked"]
        await commit(db, d)
        assert (await db.get(Resource, "locked")).data == plan


def test_original_draft_router_preview_confirm_replay_and_undo(tmp_path):
    from tests.test_foundation import make_client, register_login
    from tests.test_scheduling_constraints import confirm, seed_work, write

    with make_client(tmp_path) as c:
        headers = register_login(c)
        seed_work(c, headers)
        cid = c.get("/api/courses").json()[0]["id"]
        body = rule(course_ids=[cid])
        d = write(c, headers, "/drafts/semester-calendar", body, key="semester-preview")
        assert d.status_code == 200, d.text
        d = d.json()
        assert (
            write(
                c, headers, "/drafts/semester-calendar", body, key="semester-preview"
            ).json()
            == d
        )
        assert not c.get("/api/course-changes").json()
        assert (
            write(
                c,
                headers,
                f"/drafts/{d['id']}",
                {
                    "revision": d["revision"],
                    "payload": {**d["data"]["payload"], "reason": "retarget"},
                },
                "PUT",
            ).status_code
            == 422
        )
        assert confirm(c, headers, d, key="semester-confirm").status_code == 200
        assert confirm(c, headers, d, key="semester-confirm").status_code == 200
        batches = c.get("/api/semester-calendars").json()
        assert len(batches) == 1
        undo = write(
            c,
            headers,
            "/drafts/semester-calendar",
            {"operation": "undo", "batch_id": batches[0]["id"], "reason": "撤销通知"},
        )
        assert undo.status_code == 200, undo.text
        assert confirm(c, headers, undo.json()).status_code == 200
        assert c.get("/api/semester-calendars").json()[0]["data"]["undone_by"]
        assert not c.get("/api/course-changes").json()


async def test_persisted_preview_hash_protects_mutation_targets_and_undo_owner(
    sessions,
):
    async with sessions() as db:
        await seed(db)
        d = await draft(db, rule())
        corrupted = deepcopy(d.data)
        corrupted["source"]["preview"]["mutations"][0]["replacement"]["date"] = (
            "2026-10-28"
        )
        d.data = corrupted
        await db.flush()
        with pytest.raises(HTTPException) as error:
            await service().save_semester(db, "alice", d, d.data["payload"])
        assert error.value.status_code == 409
        assert not await store.rows(db, "alice", "exception")
        d = await draft(db, rule())
        await commit(db, d)
        batch = (await store.rows(db, "alice", "semester_calendar_batch"))[0]
        with pytest.raises(HTTPException) as error:
            await draft(
                db, {"operation": "undo", "batch_id": batch.id, "reason": "撤销"}, "bob"
            )
        assert error.value.status_code == 404


@pytest.mark.parametrize("change", ["clock", "course_periods", "timezone"])
async def test_confirmed_makeup_survives_clock_or_period_changes_and_can_undo(
    sessions, change
):
    async with sessions() as db:
        await seed(db)
        course = await db.get(Resource, "math")
        course.data = {**course.data, "periods": [1, 3], "weeks": [1]}
        await db.commit()
        d = await draft(
            db,
            rule(
                course_ids=["math"],
                action="move",
                start_date=None,
                end_date=None,
                mappings=[{"original_date": "2026-10-14", "target_date": "2026-10-18"}],
            ),
        )
        await commit(db, d)
        expected = next(
            e for e in await occurrences(db) if e["id"] == "math:2026-10-14"
        )
        if change == "clock":
            settings = await store.settings(db, "alice")
            settings.data = {
                **settings.data,
                "periods": {
                    "1": {"start": "09:10", "end": "10:10"},
                    "3": {"start": "14:10", "end": "15:10"},
                },
            }
            settings.revision += 1
        elif change == "course_periods":
            # Current unadjusted course now uses one period; its confirmed
            # makeup remains the exact two-run fact the user reviewed.
            course.data = {**course.data, "periods": [3]}
            course.revision += 1
        else:
            settings = await store.settings(db, "alice")
            settings.data = {**settings.data, "timezone": "Pacific/Honolulu"}
            settings.revision += 1
        await store.bump(db, "alice")
        await db.commit()
        actual = next(e for e in await occurrences(db) if e["id"] == "math:2026-10-14")
        assert actual == expected
        batch = (await store.rows(db, "alice", "semester_calendar_batch"))[0]
        undo = await draft(
            db,
            {"operation": "undo", "batch_id": batch.id, "reason": "恢复当前课程规则"},
        )
        await commit(db, undo)
        restored = next(
            e for e in await occurrences(db) if e["id"] == "math:2026-10-14"
        )
        assert restored["starts_at"].startswith("2026-10-14")
        assert restored["teaching_intervals"] != expected["teaching_intervals"]
