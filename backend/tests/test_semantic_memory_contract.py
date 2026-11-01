"""A stale or foreign vector hit cannot override canonical memory eligibility."""

from app import memories
from tests.test_foundation import make_client, register_login
from tests.test_memories import proposal, review, state, dbcall


def test_semantic_hits_revalidate_revision_owner_and_recall_switch(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        proposal(
            c,
            h,
            key="workstyle",
            content="夜间效率高，清晨不易专注",
            category="study_preference",
        )
        candidate = state(c)["candidates"][0]
        assert review(c, h, candidate).status_code == 200
        memory = state(c)["memories"][0]

        def recall(scores):
            return dbcall(
                c,
                lambda db, o: memories.recall(db, o, "evening", semantic_scores=scores),
            )

        assert recall(None)["items"] == []
        assert (
            recall({memory["id"]: {"score": 0.8, "revision": memory["revision"] - 1}})[
                "items"
            ]
            == []
        )
        assert recall({"foreign-id": {"score": 1, "revision": 1}})["items"] == []
        hit = {memory["id"]: {"score": 0.8, "revision": memory["revision"]}}
        assert recall(hit)["items"][0]["id"] == memory["id"]
        flags = state(c)["settings"]
        result = c.put(
            "/api/memories/preferences",
            json={
                "revision": flags["revision"],
                "recall_enabled": False,
                "suggestions_enabled": False,
            },
            headers={**h, "Idempotency-Key": "disable"},
        )
        assert result.status_code == 200
        assert recall(hit)["items"] == []


def test_forgotten_memory_never_returns_from_old_semantic_hit(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        proposal(
            c, h, key="workstyle", content="更喜欢夜晚复习", category="study_preference"
        )
        assert review(c, h, state(c)["candidates"][0]).status_code == 200
        memory = state(c)["memories"][0]
        hit = {memory["id"]: {"score": 0.9, "revision": memory["revision"]}}
        result = c.post(
            "/api/memories/" + memory["id"] + "/forget",
            json={"revision": memory["revision"]},
            headers={**h, "Idempotency-Key": "forget"},
        )
        assert result.status_code == 200
        assert review(c, h, state(c)["candidates"][0]).status_code == 200
        result = dbcall(
            c, lambda db, o: memories.recall(db, o, "evening", semantic_scores=hit)
        )
        assert result["items"] == []
        assert state(c)["memories"][0]["data"]["content"] == ""
