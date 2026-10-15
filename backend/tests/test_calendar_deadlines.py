"""Date boundaries from messages, including old pending drafts. No live model."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app import store
from app.agent import student_agent, transaction
from tests.test_agent import ToolModel
from tests.test_calendar_events import post
from tests.test_draft_usability import confirm, draft
from tests.test_foundation import make_client, register_login


@pytest.mark.parametrize(
    "wording,expected",
    [
        ("11月1日之前", "2026-11-01T00:00:00+08:00"),
        ("2027年1月1日前", "2027-01-01T00:00:00+08:00"),
        ("2026-11-01之前", "2026-11-01T00:00:00+08:00"),
        ("明年1月1日之前", "2027-01-01T00:00:00+08:00"),
        ("明天之前", "2026-10-16T00:00:00+08:00"),
    ],
)
def test_calendar_boundary_is_prefilled_and_can_save_without_entering_time(
    tmp_path, monkeypatch, wording, expected
):
    monkeypatch.setattr(
        "app.imports.now",
        lambda: datetime(2026, 10, 15, 12, tzinfo=timezone.utc),
        raising=False,
    )
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = draft(c, h, "日期回归", wording)
        item = d["data"]["payload"]["items"][0]
        assert item["due_at"] == expected
        assert item["deadline_basis"]["kind"] == "calendar_boundary"
        assert "due_at" not in item["uncertain_fields"]
        assert confirm(c, h, d, "save").status_code == 200
        assert c.get("/api/tasks").json()[0]["data"]["due_at"] == expected


def test_legacy_draft_uses_creation_year_not_refresh_year_and_get_never_saves(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = draft(c, h, "旧草稿", "11月1日之前")
        owner = c.get("/api/me").json()["id"]

        async def old_draft(read=False):
            async with transaction(c.app) as db:
                r = await store.owned(db, owner, d["id"], "draft")
                if not read:
                    data = deepcopy(r.data)
                    data["source"] = {}
                    data["payload"]["items"][0].update(
                        due_at=None, deadline_basis=None, uncertain_fields=["due_at"]
                    )
                    r.data = data
                    r.created_at = datetime(2025, 10, 15, 12, tzinfo=timezone.utc)
                return store.view(r)

        original = c.portal.call(old_draft)
        preview = c.get(f"/api/drafts/{d['id']}").json()
        assert (
            preview["data"]["suggested_payload"]["items"][0]["due_at"]
            == "2025-11-01T00:00:00+08:00"
        )
        assert c.portal.call(old_draft, True) == original
        assert c.get("/api/tasks").json() == []


@pytest.mark.parametrize("wording", ["11月1日", "11月1日左右", "2月30日之前", "周末前"])
def test_unbounded_or_invalid_date_does_not_get_an_invented_time(tmp_path, wording):
    with make_client(tmp_path) as c:
        h = register_login(c)
        item = draft(c, h, "模糊", wording)["data"]["payload"]["items"][0]
        assert item["due_at"] is None


def test_screenshot_without_confirmed_message_year_is_not_assigned_this_year(tmp_path):
    from tests.test_assignments import png

    with make_client(tmp_path) as c:
        h = register_login(c)
        asset = c.post(
            "/api/assets",
            files={"file": ("test.png", png(), "image/png")},
            headers={**h, "Idempotency-Key": "asset"},
        ).json()
        d = post(
            c,
            h,
            "/api/drafts/assignment",
            {
                "asset_id": asset["id"],
                "items": [{"title": "历史截图", "due_text": "11月1日之前"}],
            },
            str(uuid4()),
        ).json()
        assert d["data"]["payload"]["items"][0]["due_at"] is None


def test_agent_can_correct_pending_draft_to_calendar_boundary_with_no_clock(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = draft(c, h, "改期", None)
        owner = c.get("/api/me").json()["id"]
        c.app.state.agent_model_factory = lambda: ToolModel()
        tools = student_agent(c.app, owner).nodes["tools"].bound.tools_by_name
        edited = c.portal.call(
            tools["set_assignment_draft_deadline"].ainvoke,
            {
                "draft_id": d["id"],
                "revision": d["revision"],
                "item_index": 0,
                "due_text": "2026年11月1日之前",
                "due_at": None,
            },
        )
        assert (
            edited["data"]["payload"]["items"][0]["due_at"]
            == "2026-11-01T00:00:00+08:00"
        )
        assert c.get("/api/tasks").json() == []


@pytest.mark.parametrize(
    "reference,expected",
    [("2025-10-15T18:00:00+08:00", "2025-11-01T00:00:00+08:00"), (None, None)],
)
def test_image_boundary_uses_confirmed_message_date_only(tmp_path, reference, expected):
    from tests.test_assignments import png

    class ImageBoundary:
        async def extract_assignments(self, *args):
            return {
                "items": [
                    {
                        "title": "合成测试截图",
                        "due_text": "11月1日之前",
                        "due_at": None,
                        "uncertain_fields": ["due_at"],
                    }
                ]
            }

    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.gateway = ImageBoundary()
        asset = c.post(
            "/api/assets",
            files={"file": ("test.png", png(), "image/png")},
            headers={**h, "Idempotency-Key": "asset"},
        ).json()
        job = post(
            c,
            h,
            "/api/assignment-jobs",
            {"asset_id": asset["id"], "consent": True, "reference_time": reference},
            "job",
        ).json()
        job = c.get(f"/api/jobs/{job['id']}").json()
        assert job["data"]["status"] == "done"
        d = c.get(f"/api/drafts/{job['data']['draft_id']}").json()
        assert d["data"]["payload"]["items"][0]["due_at"] == expected
        assert c.get("/api/tasks").json() == []


def test_date_basis_checks_conflicts_but_allows_a_reviewed_manual_override(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = draft(c, h, "修改已推算日期", "2026年11月1日之前")
        payload = deepcopy(d["data"]["payload"])
        payload["items"][0]["due_at"] = "2026-11-02T20:00:00+08:00"

        def edit(revision, key):
            response = c.put(
                f"/api/drafts/{d['id']}",
                json={"revision": revision, "payload": payload},
                headers={**h, "Idempotency-Key": key},
            )
            assert response.status_code == 200
            return response.json()

        mismatched = edit(1, "mismatch")
        assert confirm(c, h, mismatched, "refuse-mismatch").status_code == 409
        assert c.get("/api/tasks").json() == []
        payload["items"][0]["deadline_basis"] = None
        override = edit(mismatched["revision"], "manual-override")
        assert confirm(c, h, override, "confirmed-override").status_code == 200
        assert (
            c.get("/api/tasks").json()[0]["data"]["due_at"]
            == "2026-11-02T20:00:00+08:00"
        )
