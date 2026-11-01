"""Knowledge attachment ownership and model boundary integration."""

from uuid import uuid4

from app import store
from app.db import Resource
from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login
from tests.test_memories import dbcall


def seed_source(c, text="Synthetic course material"):
    async def write(db, owner):
        r = Resource(
            owner_id=owner,
            kind="knowledge_source",
            data={
                "title": "synthetic.md",
                "filename": "synthetic.md",
                "format": "md",
                "course_id": None,
                "chunks": [{"id": "c1", "text": text, "location": "段落1"}],
            },
        )
        db.add(r)
        await db.flush()
        return store.view(r)

    return dbcall(c, write)


def thread(c, h):
    return c.post(
        "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": str(uuid4())}
    ).json()["id"]


def test_source_attachment_owner_duplicate_and_empty_message(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        source = seed_source(c)
        tid = thread(c, h)
        c.app.state.agent_model_factory = lambda: ToolModel()

        def send(ids, message=""):
            return c.post(
                "/api/agent/runs",
                json={"thread_id": tid, "message": message, "source_ids": ids},
                headers={**h, "Idempotency-Key": str(uuid4())},
            )

        assert send([source["id"], source["id"]]).status_code == 422
        assert send([str(uuid4())], "read source").status_code == 404
        result = send([source["id"]])
        assert result.status_code == 200, result.text
        run = wait_run(c, result.json()["id"])
        assert run["data"]["status"] == "done"
        assert run["data"]["source_ids"] == [source["id"]]
        assert source["id"] in c.get(f"/api/agent/runs/{run['id']}/events?after=0").text
        c.post("/api/auth/logout", headers=h)
        h = register_login(c, "other@example.com")
        tid = thread(c, h)
        assert send([source["id"]], "read source").status_code == 404
