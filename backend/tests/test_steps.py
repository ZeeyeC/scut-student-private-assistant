import pytest

from tests.test_foundation import make_client, register_login


def test_decomposition_rejects_cycle_unknown_and_allows_large_total():
    from app.tasks import validate_steps

    def step(key, deps=[]):
        return {
            "key": key,
            "title": key,
            "description": "做一项具体工作",
            "estimated_minutes": 180,
            "dependency_keys": deps,
            "acceptance_criteria": ["提交结果"],
        }

    with pytest.raises(ValueError):
        validate_steps([step("a", ["b"]), step("b", ["a"])])
    with pytest.raises(ValueError):
        validate_steps([step("a", ["missing"])])
    assert len(validate_steps([step("a"), step("b", ["a"])])) == 2


def task_and_headers(c):
    h = register_login(c)
    d = c.post(
        "/api/drafts/assignment",
        json={"items": [{"title": "报告", "requirements": []}]},
        headers={**h, "Idempotency-Key": "task-draft"},
    ).json()
    c.post(
        "/api/drafts/" + d["id"] + "/confirm",
        json={"revision": 1},
        headers={**h, "Idempotency-Key": "task-save"},
    )
    return c.get("/api/tasks").json()[0], h


def test_spent_does_not_complete_and_redecomposition_preserves_completed(tmp_path):
    with make_client(tmp_path) as c:
        t, h = task_and_headers(c)
        candidate = {
            "key": "a",
            "title": "查资料",
            "description": "找出三篇论文",
            "estimated_minutes": 60,
            "dependency_keys": [],
            "acceptance_criteria": ["列出三篇论文"],
        }

        def save_steps(key):
            task = c.get("/api/tasks/" + t["id"]).json()
            d = c.post(
                "/api/tasks/" + t["id"] + "/step-drafts",
                json={"task_revision": task["revision"], "steps": [candidate]},
                headers={**h, "Idempotency-Key": key},
            ).json()
            assert (
                c.post(
                    "/api/drafts/" + d["id"] + "/confirm",
                    json={"revision": 1},
                    headers={**h, "Idempotency-Key": key + "confirm"},
                ).status_code
                == 200
            )

        save_steps("s1")
        step = c.get("/api/tasks/" + t["id"] + "/steps").json()[0]
        url = "/api/steps/" + step["id"]
        got = c.patch(
            url,
            json={"revision": 1, "spent_minutes": 60},
            headers={**h, "Idempotency-Key": "spent"},
        ).json()
        assert got["data"]["status"] == "open"
        assert got["data"]["spent_minutes"] == 60
        assert (
            c.patch(
                url,
                json={"revision": 1, "status": "completed"},
                headers={**h, "Idempotency-Key": "stale"},
            ).status_code
            == 409
        )
        assert (
            c.patch(
                url,
                json={"revision": got["revision"], "status": "completed"},
                headers={**h, "Idempotency-Key": "complete"},
            ).status_code
            == 200
        )
        save_steps("s2")
        assert any(
            s["id"] == step["id"] and s["data"]["status"] == "completed"
            for s in c.get("/api/tasks/" + t["id"] + "/steps").json()
        )
