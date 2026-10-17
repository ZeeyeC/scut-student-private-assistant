from uuid import uuid4

import pytest

from app.agent import emit
from app.db import Resource
from tests.test_foundation import make_client, register_login


def seed_run(c, status="running", event=None):
    owner = c.get("/api/me").json()["id"]
    tid, rid = str(uuid4()), str(uuid4())

    async def seed():
        async with c.app.state.sessions() as db:
            db.add(
                Resource(
                    id=tid,
                    owner_id=owner,
                    kind="agent_thread",
                    data={"title": "private"},
                )
            )
            db.add(
                Resource(
                    id=rid,
                    owner_id=owner,
                    kind="agent_run",
                    data={
                        "thread_id": tid,
                        "status": status,
                        "message": "private text",
                        "event_counter": 0,
                    },
                )
            )
            await db.flush()
            if event:
                await emit(db, owner, rid, event, {"delta": "private response"})
            await db.commit()

    c.portal.call(seed)
    return tid, rid


@pytest.mark.parametrize(
    "status,event,want",
    [
        ("queued", None, "thinking"),
        ("running", None, "thinking"),
        ("resume_queued", None, "thinking"),
        ("running", "message_delta", "replying"),
        ("running", "tool_started", "thinking"),
        ("waiting_approval", None, "approval"),
        ("done", "message_delta", "idle"),
        ("failed", None, "idle"),
    ],
)
def test_authoritative_state_without_chat_page(tmp_path, status, event, want):
    with make_client(tmp_path) as c:
        register_login(c)
        tid, _ = seed_run(c, status, event)
        response = c.get("/api/agent/pet-state")
        assert response.status_code == 200, response.text
        assert response.json() == {
            "state": want,
            "review_thread_id": tid if want == "approval" else None,
        }
        assert "private" not in response.text


def test_approval_priority_and_non_default_thread_are_preserved(tmp_path):
    with make_client(tmp_path) as c:
        register_login(c)
        pending, _ = seed_run(c, "waiting_approval")
        seed_run(c, "running", "message_delta")
        assert c.get("/api/agent/pet-state").json() == {
            "state": "approval",
            "review_thread_id": pending,
        }


def test_state_and_pending_drafts_are_owner_scoped(tmp_path):
    with make_client(tmp_path) as c:
        assert c.get("/api/agent/pet-state").status_code == 401
        h = register_login(c)
        draft = c.post(
            "/api/drafts/assignment",
            json={"items": [{"title": "private"}]},
            headers={**h, "Idempotency-Key": "draft"},
        )
        assert draft.status_code == 200
        assert c.get("/api/agent/pet-state").json() == {
            "state": "approval",
            "review_thread_id": None,
        }
        c.post("/api/auth/logout", headers=h)
        register_login(c, "other@example.com")
        assert c.get("/api/agent/pet-state").json() == {
            "state": "idle",
            "review_thread_id": None,
        }
