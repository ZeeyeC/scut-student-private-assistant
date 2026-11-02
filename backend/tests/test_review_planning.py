"""Accepted review intents create real A drafts and retain real approval evidence."""

from copy import deepcopy

import pytest

from tests.test_goal_capacity import (
    clock,  # Import the shared autouse fixture along with its fixed-date helpers.
    headers,
    linked_client,
    resources,
    seed,
    settings,
)


def test_elapsed_next_week_still_rejects_generation_without_creating_draft(tmp_path, monkeypatch):
    from datetime import datetime
    from app import weekly_review
    with linked_client(tmp_path) as c:
        work(c)
        action(c)
        monkeypatch.setattr(weekly_review, "now", lambda: datetime.fromisoformat("2026-11-02T00:00:00+08:00"))
        response = generate(c)
        assert response.status_code == 422
        assert resources(c, "draft") == []


def report(c, week="2026-10-26", owner="alice", zone="Asia/Shanghai"):
    response = c.get(
        f"/api/weekly-review?week_start={week}&timezone={zone}",
        headers=headers(owner=owner),
    )
    assert response.status_code == 200, response.text
    return response.json()


def action(
    c, choice="accept", key="accept", reason="下周把学习提前", week="2026-10-26"
):
    current = report(c, week)
    body = {
        "week_start": week,
        "timezone": "Asia/Shanghai",
        "revision": current["review"]["revision"],
        "source_revision": current["source_revision"],
        "action": choice,
        "reason": reason,
    }
    response = c.post("/api/weekly-review/actions", headers=headers(key), json=body)
    assert response.status_code == 200, response.text
    return response.json()


def request_body(c, week="2026-10-26"):
    current = report(c, week)
    return {
        "week_start": week,
        "timezone": "Asia/Shanghai",
        "revision": current["review"]["revision"],
        "source_revision": current["source_revision"],
    }


def work(c):
    seed(
        c,
        settings(),
        (
            "task",
            "task",
            {"title": "复习", "status": "open", "priority": 2, "due_at": None},
            "alice",
        ),
        (
            "step",
            "step",
            {
                "title": "复习第一章",
                "task_id": "task",
                "estimated_minutes": 60,
                "spent_minutes": 0,
                "dependency_ids": [],
                "status": "open",
            },
            "alice",
        ),
    )


def generate(c, body=None, key="generate", owner="alice"):
    return c.post(
        "/api/weekly-review/plan-draft",
        headers=headers(key, owner),
        json=body or request_body(c),
    )


def test_review_generates_actual_next_week_draft_once_then_confirms_through_original_route(
    tmp_path,
):
    with linked_client(tmp_path) as c:
        work(c)
        seed(
            c,
            (
                "original-snapshot",
                "plan_snapshot",
                {
                    "draft_id": "historic-draft",
                    "approved_at": "2026-10-25T02:00:00+00:00",
                    "approved_plan": {
                        "target_date": "2026-10-26",
                        "horizon_days": 7,
                        "timezone": "Asia/Shanghai",
                        "blocks": [
                            {
                                "id": "reviewed-block",
                                "task_id": "task",
                                "step_id": "step",
                                "title": "原始复习",
                                "starts_at": "2026-10-26T09:00:00+08:00",
                                "ends_at": "2026-10-26T10:00:00+08:00",
                            }
                        ],
                    },
                },
                "alice",
            ),
            (
                "actual-fact",
                "execution",
                {
                    "task_id": "task",
                    "step_id": "step",
                    "plan_block_id": "reviewed-block",
                    "performed_on": "2026-10-26",
                    "timezone": "Asia/Shanghai",
                    "actual_minutes": 25,
                    "feedback": "partial",
                    "unfinished_reason": None,
                    "source": "manual",
                    "supersedes_id": None,
                },
                "alice",
            ),
        )
        historical_snapshots = deepcopy(resources(c, "plan_snapshot"))
        actual_facts = deepcopy(resources(c, "execution"))
        original = report(c)
        assert original["plans"]["original"]["minutes"] == 60
        assert original["execution"]["actual_seconds"] == 1500
        action(c)
        body = request_body(c)
        response = generate(c, body)
        assert response.status_code == 200, response.text
        saved = response.json()
        draft = saved["draft"]
        assert draft["data"]["draft_kind"] == "plan"
        assert draft["data"]["payload"]["target_date"] == "2026-11-02"
        assert draft["data"]["payload"]["horizon_days"] == 7
        assert draft["data"]["payload"]["blocks"]
        assert draft["data"]["source"]["weekly_review_id"] == saved["review"]["id"]
        assert len(resources(c, "draft")) == 1
        assert resources(c, "plan_block") == []
        assert resources(c, "plan_snapshot") == historical_snapshots
        assert resources(c, "execution") == actual_facts
        assert generate(c, body).json() == saved
        assert len(resources(c, "draft")) == 1
        pending = report(c)
        assert pending["next_week_plan"]["status"] == "pending"
        assert pending["next_week_plan"]["draft"]["id"] == draft["id"]
        assert pending["plans"] == original["plans"]
        assert pending["execution"] == original["execution"]
        # A refreshed new key does not supersede the same live linked draft.
        repeated = generate(c, key="second-key")
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["draft"]["id"] == draft["id"]
        assert len(resources(c, "draft")) == 1
        approved = c.post(
            f"/api/drafts/{draft['id']}/confirm",
            headers=headers("confirm"),
            json={"revision": draft["revision"]},
        )
        assert approved.status_code == 200, approved.text
        confirmed = report(c)
        assert confirmed["next_week_plan"]["status"] == "confirmed"
        assert len(confirmed["next_week_plan"]["snapshot_ids"]) == 1
        blocks = deepcopy(resources(c, "plan_block"))
        snapshots = deepcopy(resources(c, "plan_snapshot"))
        assert blocks and len(snapshots) == 2
        assert historical_snapshots[0] in snapshots
        assert resources(c, "execution") == actual_facts
        action(c, "restore", "restore", reason=None)
        restored = report(c)
        assert restored["review"]["data"]["status"] == "awaiting_choice"
        assert restored["next_week_plan"]["status"] == "confirmed"
        assert resources(c, "plan_block") == blocks
        assert resources(c, "plan_snapshot") == snapshots
        assert restored["plans"] == original["plans"]
        assert restored["execution"] == original["execution"]
    with linked_client(tmp_path) as c:
        assert report(c)["next_week_plan"]["status"] == "confirmed"
        assert report(c)["review"]["data"]["plan_links"][0]["draft_id"] == draft["id"]


def test_review_planning_requires_accepted_intent_current_versions_and_matching_owner(
    tmp_path,
):
    with linked_client(tmp_path) as c:
        work(c)
        assert generate(c).status_code == 409
        action(c)
        body = request_body(c)
        assert generate(c, {**body, "revision": 0}, "old-review").status_code == 409
        assert (
            generate(c, {**body, "source_revision": 0}, "old-source").status_code == 409
        )
        assert generate(c, body, owner="bob").status_code == 409
        assert generate(c, {**body, "timezone": "UTC"}, "wrong-zone").status_code == 409
        assert resources(c, "draft") == []
        # Same receipt key with different content is rejected rather than replayed.
        saved = generate(c, body)
        assert saved.status_code == 200, saved.text
        assert (
            generate(c, {**body, "revision": body["revision"] + 1}).status_code == 409
        )


def test_source_changes_invalidate_link_and_original_confirmation_and_restore_preserves_history(
    tmp_path,
):
    with linked_client(tmp_path) as c:
        work(c)
        action(c)
        saved = generate(c)
        assert saved.status_code == 200, saved.text
        draft = saved.json()["draft"]
        # A new explicit review choice advances the common facts version.
        action(c, "reason", "new-reason", "补充原因")
        invalid = report(c)
        assert invalid["next_week_plan"]["status"] == "invalidated"
        assert invalid["next_week_plan"]["reason"] == "source_changed"
        assert (
            c.post(
                f"/api/drafts/{draft['id']}/confirm",
                headers=headers("stale-confirm"),
                json={"revision": draft["revision"]},
            ).status_code
            == 409
        )
        stale_body = {
            **request_body(c),
            "source_revision": draft["data"]["source_revision"],
        }
        assert generate(c, stale_body, "stale-plan").status_code == 409
        assert resources(c, "plan_block") == resources(c, "plan_snapshot") == []
        regenerated = generate(c, key="regenerate")
        assert regenerated.status_code == 200, regenerated.text
        assert regenerated.json()["draft"]["id"] != draft["id"]
        assert len(report(c)["review"]["data"]["plan_links"]) == 2
        action(c, "restore", "restore", None)
        restored = report(c)
        assert len(restored["review"]["data"]["plan_links"]) == 2
        assert restored["next_week_plan"]["status"] == "invalidated"
        assert generate(c, key="after-restore").status_code == 409


def test_past_target_week_rejected_and_timezone_year_boundary_uses_reviewed_week_plus_seven(
    tmp_path,
):
    with linked_client(tmp_path) as c:
        work(c)
        action(c, week="2026-10-19")
        response = generate(c, request_body(c, "2026-10-19"))
        assert response.status_code == 422, response.text
        assert resources(c, "draft") == []
        action(c, key="year", week="2026-12-28")
        saved = generate(c, request_body(c, "2026-12-28"), "year-plan")
        assert saved.status_code == 200, saved.text
        assert saved.json()["draft"]["data"]["payload"]["target_date"] == "2027-01-04"
        assert saved.json()["draft"]["data"]["payload"]["timezone"] == "Asia/Shanghai"


def test_a_new_explicit_acceptance_can_generate_a_new_draft_after_confirmed_history(
    tmp_path,
):
    with linked_client(tmp_path) as c:
        work(c)
        action(c)
        first = generate(c)
        assert first.status_code == 200, first.text
        draft = first.json()["draft"]
        assert (
            c.post(
                f"/api/drafts/{draft['id']}/confirm",
                headers=headers("confirm"),
                json={"revision": draft["revision"]},
            ).status_code
            == 200
        )
        snapshots = deepcopy(resources(c, "plan_snapshot"))
        blocks = deepcopy(resources(c, "plan_block"))
        action(c, "accept", "new-accept", "重新核对下周安排")
        second = generate(c, key="new-plan")
        assert second.status_code == 200, second.text
        assert second.json()["draft"]["id"] != draft["id"]
        assert len(report(c)["review"]["data"]["plan_links"]) == 2
        assert resources(c, "plan_snapshot") == snapshots
        assert resources(c, "plan_block") == blocks


def test_generation_failure_rolls_back_draft_link_event_and_receipt_then_can_retry(
    tmp_path, monkeypatch
):
    from app import weekly_review

    with linked_client(tmp_path) as c:
        work(c)
        action(c)
        before = deepcopy(resources(c))
        body = request_body(c)
        record = weekly_review.record_change

        async def fail(*args, **kwargs):
            raise RuntimeError("synthetic link event failure")

        monkeypatch.setattr(weekly_review, "record_change", fail)
        with pytest.raises(RuntimeError, match="synthetic link"):
            generate(c, body)
        assert resources(c) == before
        monkeypatch.setattr(weekly_review, "record_change", record)
        retried = generate(c, body)
        assert retried.status_code == 200, retried.text
        assert len(resources(c, "draft")) == 1
        assert len(report(c)["review"]["data"]["plan_links"]) == 1
        assert generate(c, body).json() == retried.json()


def test_link_read_detects_deleted_superseded_and_tampered_drafts_without_writes(
    tmp_path,
):
    with linked_client(tmp_path) as c:
        work(c)
        action(c)
        first = generate(c)
        assert first.status_code == 200, first.text
        draft = first.json()["draft"]

        async def tamper():
            async with c.app.state.sessions() as db:
                from app.db import Resource

                resource = await db.get(Resource, draft["id"])
                resource.data = {
                    **resource.data,
                    "payload": {**resource.data["payload"], "horizon_days": 6},
                }
                await db.commit()

        c.portal.call(tamper)
        before = resources(c)
        assert report(c)["next_week_plan"]["reason"] == "draft_changed"
        assert resources(c) == before
        second = generate(c, key="replacement")
        assert second.status_code == 200, second.text
        external = c.post(
            "/api/plan-drafts",
            headers=headers("external"),
            json={"target_date": "2026-11-02", "horizon_days": 7},
        )
        assert external.status_code == 200, external.text
        assert report(c)["next_week_plan"]["reason"] == "draft_superseded"
        third = generate(c, key="again")
        assert third.status_code == 200, third.text
        draft_id = third.json()["draft"]["id"]

        async def delete():
            async with c.app.state.sessions() as db:
                from app.db import Resource

                await db.delete(await db.get(Resource, draft_id))
                await db.commit()

        c.portal.call(delete)
        assert report(c)["next_week_plan"]["reason"] == "draft_unavailable"
        assert resources(c, "plan_block") == resources(c, "plan_snapshot") == []
