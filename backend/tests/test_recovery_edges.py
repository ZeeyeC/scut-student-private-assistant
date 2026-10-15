from tests.test_agent import ToolModel, wait_run
from tests.test_browser_import import configured_client
from tests.test_foundation import make_client, register_login


def test_reject_does_not_commit_and_stale_approval_fails(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: ToolModel()
        for suffix, decision in [("reject", "reject"), ("stale", "approve")]:
            d = c.post(
                "/api/drafts/assignment",
                json={"items": [{"title": "报告", "requirements": []}]},
                headers={**h, "Idempotency-Key": "draft" + suffix},
            ).json()
            t = c.post(
                "/api/agent/threads",
                json={},
                headers={**h, "Idempotency-Key": "thread" + suffix},
            ).json()
            r = c.post(
                "/api/agent/runs",
                json={"thread_id": t["id"], "message": "commit:" + d["id"]},
                headers={**h, "Idempotency-Key": "run" + suffix},
            ).json()
            r = wait_run(c, r["id"])
            a = c.get("/api/agent/approvals/" + r["data"]["approval_id"]).json()
            if suffix == "stale":
                # The actual approved draft changed, rather than unrelated settings.
                c.put(
                    "/api/drafts/" + d["id"],
                    json={
                        "revision": d["revision"],
                        "payload": {"items": [{"title": "更改后的报告"}]},
                    },
                    headers={**h, "Idempotency-Key": "change"},
                )
            assert (
                c.post(
                    "/api/agent/runs/" + r["id"] + "/resume",
                    json={
                        "approval_id": a["id"],
                        "revision": a["revision"],
                        "decision": decision,
                    },
                    headers={**h, "Idempotency-Key": "resume" + suffix},
                ).status_code
                == 200
            )
            end = wait_run(c, r["id"])
            assert c.get("/api/tasks").json() == []
            if suffix == "stale":
                assert end["data"]["status"] == "failed"


def test_browser_import_owner_and_out_of_order(tmp_path):
    with configured_client(tmp_path) as c:
        h = register_login(c)
        b = c.post(
            "/api/browser-imports",
            json={"school_id": "scut"},
            headers={**h, "Idempotency-Key": "b"},
        ).json()
        url = "/api/browser-imports/" + b["id"]
        assert (
            c.post(
                url + "/events",
                json={"kind": "extracting", "event_id": "wrong", "revision": 1},
                headers={**h, "Idempotency-Key": "wrong"},
            ).status_code
            == 409
        )
        c.post("/api/auth/logout", headers=h)
        h2 = register_login(c, "bob@example.com")
        assert c.get(url).status_code == 404
        assert (
            c.post(
                url + "/cancel",
                json={"revision": 1},
                headers={**h2, "Idempotency-Key": "cancel"},
            ).status_code
            == 404
        )


def test_plan_source_revision_and_completion_receipt(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        d = c.post(
            "/api/plan-drafts", json={}, headers={**h, "Idempotency-Key": "plan"}
        ).json()
        s = c.get("/api/settings").json()
        c.put("/api/settings", json=s, headers={**h, "Idempotency-Key": "settings"})
        assert (
            c.post(
                "/api/drafts/" + d["id"] + "/confirm",
                json={"revision": 1},
                headers={**h, "Idempotency-Key": "stale"},
            ).status_code
            == 409
        )
