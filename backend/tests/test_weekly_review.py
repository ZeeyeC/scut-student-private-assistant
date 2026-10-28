"""Weekly facts use isolated SQLite and the public API; no personal DB or model."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, Resource


def client(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/review.db")
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

    async def user(x_test_owner: str | None = Header(default=None)):
        if not x_test_owner:
            raise HTTPException(401)
        return SimpleNamespace(id=x_test_owner)

    from app.review_routes import review_router

    app.include_router(review_router(db_session, user))
    return TestClient(app)


def seed(c, *items):
    async def write():
        async with c.app.state.sessions() as db:
            db.add_all(
                [
                    Resource(id=rid, owner_id=owner, kind=kind, data=data)
                    for rid, kind, data, owner in items
                ]
            )
            await db.commit()

    c.portal.call(write)


def r(rid, kind, data, owner="alice"):
    return rid, kind, data, owner


def block(rid="b", minutes=60, starts="2026-10-26T10:00:00+08:00", ends=None):
    from datetime import datetime, timedelta

    return {
        "id": rid,
        "task_id": "task",
        "step_id": "step",
        "title": "复习",
        "starts_at": starts,
        "ends_at": ends
        or (datetime.fromisoformat(starts) + timedelta(minutes=minutes)).isoformat(),
        "status": "planned",
    }


def snapshot(
    rid="snap",
    blocks=None,
    start="2026-10-26",
    days=7,
    approved="2026-10-25T10:00:00+08:00",
    timezone="Asia/Shanghai",
):
    return r(
        rid,
        "plan_snapshot",
        {
            "approved_at": approved,
            "approved_plan": {
                "target_date": start,
                "horizon_days": days,
                "timezone": timezone,
                "blocks": blocks if blocks is not None else [block()],
            },
            "previous_blocks": [],
        },
    )


def fact(rid="e", minutes=25, **changes):
    return r(
        rid,
        "execution",
        {
            "task_id": "task",
            "step_id": "step",
            "plan_block_id": "b",
            "performed_on": "2026-10-26",
            "timezone": "Asia/Shanghai",
            "actual_minutes": minutes,
            "feedback": "partial",
            "unfinished_reason": None,
            "source": "manual",
            "supersedes_id": None,
            **changes,
        },
    )


def read(c, week="2026-10-26", timezone=None, owner="alice"):
    response = c.get(
        "/api/weekly-review",
        params={"week_start": week, **({"timezone": timezone} if timezone else {})},
        headers={"X-Test-Owner": owner},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_original60_actual25_corrected20_is_append_only_and_traced(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            r("settings", "settings", {"timezone": "Asia/Shanghai"}),
            r("task", "task", {"title": "数学", "status": "open"}),
            snapshot(),
            r("b", "plan_block", block()),
            fact(),
        )
        first = read(c)
        assert first["plans"]["original"]["minutes"] == 60
        assert first["execution"]["actual_seconds"] == 1500
        assert first["execution"]["observed_seconds"] == 1500
        seed(c, fact("e2", 20, supersedes_id="e", unfinished_reason="interrupted"))
        result = read(c)
        assert result["execution"]["actual_seconds"] == 1200
        assert result["execution"]["effective_record_ids"] == ["e2"]
        assert result["execution"]["records"][0]["supersedes_id"] == "e"
        assert result["execution"]["records"][0]["unfinished_reason"] == "interrupted"
        assert result["execution"]["completed_task_ids"] == []
        assert result["plans"]["original"]["snapshot_ids"] == ["snap"]
        assert read(c, owner="bob")["execution"]["actual_seconds"] is None


def test_missing_is_unknown_explicit_zero_and_estimate_stay_distinct(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            r("settings", "settings", {"timezone": "Asia/Shanghai"}),
            r("b", "plan_block", block()),
            r("step", "step", {"task_id": "task", "spent_minutes": 40}),
            r(
                "baseline",
                "execution_baseline",
                {"step_id": "step", "allocations": {"b": 40}, "unallocated_minutes": 0},
            ),
        )
        missing = read(c)
        assert missing["plans"]["original"]["minutes"] is None
        assert missing["plans"]["original"]["status"] == "missing"
        assert missing["execution"]["actual_seconds"] is None
        assert missing["execution"]["missing_plan_block_ids"] == ["b"]
        assert missing["estimates"]["allocated_minutes"] == 40
        seed(c, fact(minutes=0, feedback="not_started"))
        zero = read(c)
        assert zero["execution"]["actual_seconds"] == 0
        assert zero["estimates"]["allocated_minutes"] == 0
        assert zero["execution"]["records"][0]["reason_prompt"]


def test_partial_daily_snapshots_never_claim_full_original_and_deduplicate(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            snapshot(days=1, approved="2026-10-26T09:00:00+08:00"),
            snapshot(
                "later",
                [block(minutes=30), block(minutes=30)],
                days=1,
                approved="2026-10-26T09:30:00+08:00",
            ),
        )
        result = read(c)
        assert result["plans"]["original"]["status"] == "partial"
        assert result["plans"]["original"]["minutes"] is None
        assert result["plans"]["original"]["known_minutes"] == 60
        assert result["plans"]["adjusted"]["known_minutes"] == 30
        assert result["plans"]["adjusted"]["snapshot_ids"] == ["later"]
        assert "incomplete_original_baseline" in result["gaps"]


def test_full_snapshot_adjustment_does_not_double_count_retained_blocks(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            snapshot(),
            snapshot(
                "later", [block(minutes=30)], approved="2026-10-26T09:00:00+08:00"
            ),
            r("b", "plan_block", block(minutes=30)),
            fact(),
        )
        result = read(c)
        assert result["plans"]["original"]["minutes"] == 60
        assert result["plans"]["adjusted"]["minutes"] == 30
        assert result["plans"]["current"]["minutes"] == 30
        assert result["execution"]["observed_seconds"] == 1500


def test_timer_segments_split_exactly_at_local_year_boundary_and_exclude_next_monday(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(
            c,
            r("settings", "settings", {"timezone": "Asia/Shanghai"}),
            r(
                "timer",
                "execution_timer",
                {
                    "segments": [
                        {
                            "starts_at": "2026-12-27T23:59:00+08:00",
                            "ends_at": "2026-12-28T00:01:00+08:00",
                            "seconds": 120,
                        }
                    ]
                },
            ),
            fact(
                "timer-fact",
                2,
                source="timer",
                timer_id="timer",
                actual_seconds=120,
                plan_block_id=None,
                performed_on="2026-12-27",
            ),
            fact("next", 5, performed_on="2027-01-04", plan_block_id=None),
        )
        assert read(c, "2026-12-21")["execution"]["actual_seconds"] == 60
        report = read(c, "2026-12-28")
        assert report["execution"]["actual_seconds"] == 60
        assert report["week_end"] == "2027-01-04"
        assert report["execution"]["effective_record_ids"] == ["timer-fact"]


def test_timezone_change_manual_boundary_is_unknown_and_unconfirmed_timer_keeps_subtotal(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(
            c,
            r("settings", "settings", {"timezone": "UTC"}),
            fact("ambiguous", 15, performed_on="2026-10-26", plan_block_id=None),
            r(
                "timer",
                "execution_timer",
                {
                    "segments": [
                        {
                            "starts_at": "2026-10-27T10:00:00Z",
                            "ends_at": "2026-10-27T10:01:00Z",
                            "seconds": 60,
                        }
                    ]
                },
            ),
            fact(
                "offline",
                1,
                source="timer",
                timer_id="timer",
                actual_seconds=60,
                unconfirmed_interval=True,
                performed_on="2026-10-27",
                timezone="UTC",
                plan_block_id=None,
            ),
        )
        report = read(c)
        assert report["execution"]["actual_seconds"] is None
        assert report["execution"]["observed_seconds"] == 60
        assert report["execution"]["ambiguous_record_ids"] == ["ambiguous"]
        assert report["execution"]["unconfirmed_execution_ids"] == ["offline"]
        assert report["execution"]["records"][0]["actual_seconds"] is None
        own_zone = read(c, timezone="Asia/Shanghai")
        assert own_zone["execution"]["ambiguous_record_ids"] == []


def test_bad_timer_timestamps_do_not_spread_observed_seconds_across_weeks(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            r(
                "timer",
                "execution_timer",
                {
                    "segments": [
                        {
                            "starts_at": "2026-10-25T23:59:00+08:00",
                            "ends_at": "2026-10-26T00:30:00+08:00",
                            "seconds": 60,
                        }
                    ]
                },
            ),
            fact(
                source="timer", timer_id="timer", actual_seconds=60, plan_block_id=None
            ),
        )
        result = read(c)
        assert result["execution"]["actual_seconds"] is None
        assert result["execution"]["ambiguous_record_ids"] == ["e"]


@pytest.mark.parametrize(
    "query",
    [
        "week_start=2026-10-27",
        "week_start=invalid",
        "week_start=2026-10-26&timezone=Not/AZone",
    ],
)
def test_invalid_week_or_zone_is_rejected(tmp_path, query):
    with client(tmp_path) as c:
        assert (
            c.get(
                "/api/weekly-review?" + query, headers={"X-Test-Owner": "alice"}
            ).status_code
            == 422
        )
        assert c.get("/api/weekly-review?week_start=2026-10-26").status_code == 401


def test_review_intents_are_versioned_idempotent_owned_and_survive_restart(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            r("settings", "settings", {"timezone": "Asia/Shanghai"}),
            r("b", "plan_block", block()),
        )
        before = read(c)
        body = {
            "week_start": "2026-10-26",
            "timezone": "Asia/Shanghai",
            "revision": 0,
            "source_revision": before["source_revision"],
            "action": "accept",
            "reason": "下周想把晚间学习前移",
        }
        h = {"X-Test-Owner": "alice", "Idempotency-Key": "same"}
        saved = c.post("/api/weekly-review/actions", json=body, headers=h)
        assert saved.status_code == 200, saved.text
        assert saved.json()["data"]["status"] == "accepted_pending_integration"
        assert (
            c.post("/api/weekly-review/actions", json=body, headers=h).json()
            == saved.json()
        )
        assert (
            c.post(
                "/api/weekly-review/actions",
                json=body,
                headers={**h, "Idempotency-Key": "stale"},
            ).status_code
            == 409
        )
        assert read(c)["plans"]["current"] == before["plans"]["current"]
        assert read(c, owner="bob")["review"]["revision"] == 0
        rejected = {
            **body,
            "revision": 1,
            "source_revision": read(c)["source_revision"],
            "action": "reject",
        }
        response = c.post(
            "/api/weekly-review/actions",
            json=rejected,
            headers={**h, "Idempotency-Key": "reject"},
        )
        assert response.json()["data"]["status"] == "rejected"
        assert read(c)["review"]["revision"] == 2
    with client(tmp_path) as restarted:
        report = read(restarted)
        assert report["review"]["revision"] == 2
        assert len(report["review"]["data"]["history"]) == 2
        restored = {
            **body,
            "revision": 2,
            "source_revision": report["source_revision"],
            "action": "restore",
        }
        response = restarted.post(
            "/api/weekly-review/actions",
            json=restored,
            headers={**h, "Idempotency-Key": "restore"},
        )
        assert response.json()["data"]["status"] == "awaiting_choice"


def test_unknown_duration_is_not_zero_even_if_dated_and_empty_reads_do_not_write(
    tmp_path,
):
    with client(tmp_path) as c:
        empty = read(c)
        assert empty["execution"]["observed_seconds"] is None

        async def rows():
            async with c.app.state.sessions() as db:
                return list((await db.scalars(select(Resource))).all())

        assert c.portal.call(rows) == []
        item = fact()
        del item[2]["actual_minutes"]
        seed(c, item)
        result = read(c)
        assert result["execution"]["actual_seconds"] is None
        assert result["execution"]["observed_seconds"] is None
        assert result["execution"]["ambiguous_record_ids"] == ["e"]


def test_seconds_sum_before_minutes_and_only_dated_completion_facts_count(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            fact(
                "a",
                0,
                actual_seconds=59,
                plan_block_id=None,
                feedback="completed",
                task_status="completed",
            ),
            fact("b", 0, actual_seconds=59, plan_block_id=None, feedback="completed"),
            r("undated", "task", {"status": "completed", "title": "无完成日期"}),
        )
        result = read(c)
        assert result["execution"]["actual_seconds"] == 118
        assert result["execution"]["actual_minutes"] == pytest.approx(118 / 60)
        assert result["execution"]["completed_task_ids"] == ["task"]
        assert result["execution"]["undated_completed_task_ids"] == ["undated"]


def test_dst_week_uses_local_midnights_and_boundary_estimate_is_not_counted_twice(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(
            c,
            r("settings", "settings", {"timezone": "America/New_York"}),
            r("b", "plan_block", block(starts="2026-11-01T23:30:00-05:00", minutes=60)),
            r("step", "step", {"task_id": "task", "spent_minutes": 60}),
            r(
                "baseline",
                "execution_baseline",
                {"step_id": "step", "allocations": {"b": 60}, "unallocated_minutes": 0},
            ),
        )
        report = read(c, "2026-10-26")
        assert report["starts_at"] == "2026-10-26T04:00:00+00:00"
        assert report["ends_at"] == "2026-11-02T05:00:00+00:00"
        assert report["plans"]["current"]["minutes"] == 30
        assert report["estimates"]["allocated_minutes"] == 0
        assert report["estimates"]["unallocated"][0]["week_attribution"] == "unknown"


def test_review_action_failure_rolls_back_revision_receipt_and_intent(
    tmp_path, monkeypatch
):
    from app import weekly_review

    with client(tmp_path) as c:
        before = read(c)
        body = {
            "week_start": "2026-10-26",
            "timezone": "Asia/Shanghai",
            "revision": 0,
            "source_revision": 0,
            "action": "reason",
            "reason": "课程临时延长",
        }
        h = {"X-Test-Owner": "alice", "Idempotency-Key": "reason"}

        async def fail(*args, **kwargs):
            raise RuntimeError("synthetic review event failure")

        original = weekly_review.record_change
        monkeypatch.setattr(weekly_review, "record_change", fail)
        with pytest.raises(RuntimeError, match="synthetic review"):
            c.post("/api/weekly-review/actions", json=body, headers=h)
        assert read(c) == before
        monkeypatch.setattr(weekly_review, "record_change", original)
        assert (
            c.post("/api/weekly-review/actions", json=body, headers=h).status_code
            == 200
        )
        assert read(c)["review"]["revision"] == 1
        assert (
            c.post(
                "/api/weekly-review/actions",
                json={**body, "reason": "changed"},
                headers=h,
            ).status_code
            == 409
        )
        assert (
            c.post(
                "/api/weekly-review/actions",
                json={**body, "revision": 1},
                headers={**h, "Idempotency-Key": "oldsource"},
            ).status_code
            == 409
        )


def test_zero_timer_feedback_is_a_fact_and_cross_week_fractional_seconds_do_not_inflate_total(
    tmp_path,
):
    with client(tmp_path) as c:
        seed(
            c,
            r(
                "zero",
                "execution_timer",
                {
                    "segments": [
                        {
                            "starts_at": "2026-10-26T12:00:00+08:00",
                            "ends_at": "2026-10-26T12:00:00+08:00",
                            "seconds": 0,
                        }
                    ]
                },
            ),
            fact(
                "zero-e",
                0,
                source="timer",
                timer_id="zero",
                actual_seconds=0,
                feedback="not_started",
                plan_block_id=None,
            ),
        )
        assert read(c)["execution"]["actual_seconds"] == 0
    with client(tmp_path / "fractional") as c:
        seed(
            c,
            r(
                "timer",
                "execution_timer",
                {
                    "segments": [
                        {
                            "starts_at": "2026-10-25T23:59:00.500000+08:00",
                            "ends_at": "2026-10-26T00:00:59.400000+08:00",
                            "seconds": 118.9,
                        }
                    ]
                },
            ),
            fact(
                source="timer", timer_id="timer", actual_seconds=118, plan_block_id=None
            ),
        )
        prior = read(c, "2026-10-19")["execution"]["actual_seconds"]
        current = read(c)["execution"]["actual_seconds"]
        assert prior + current == 118
        assert isinstance(prior, int) and isinstance(current, int)


def test_cross_week_timer_completion_is_not_counted_as_two_completed_tasks(tmp_path):
    with client(tmp_path) as c:
        seed(
            c,
            r(
                "timer",
                "execution_timer",
                {
                    "segments": [
                        {
                            "starts_at": "2026-10-25T23:59:00+08:00",
                            "ends_at": "2026-10-26T00:01:00+08:00",
                            "seconds": 120,
                        }
                    ]
                },
            ),
            fact(
                source="timer",
                timer_id="timer",
                actual_seconds=120,
                performed_on="2026-10-25",
                feedback="completed",
                task_status="completed",
                plan_block_id=None,
            ),
        )
        for week in ("2026-10-19", "2026-10-26"):
            result = read(c, week)
            assert result["execution"]["actual_seconds"] == 60
            assert result["execution"]["completed_task_ids"] == []
            assert result["execution"]["ambiguous_completion_record_ids"] == ["e"]
