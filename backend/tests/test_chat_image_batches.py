"""Isolated multi-image regression; deterministic gateways, never paid providers."""

import time
from uuid import uuid4

from tests.test_agent import wait_run
from tests.test_chat_images import ImageVision, post, setup, upload
from tests.test_foundation import make_client, register_login


def batch(c, h, tid, ids, **extra):
    return post(
        c,
        h,
        "/agent/runs",
        {
            "thread_id": tid,
            "attachments": [{"asset_id": a, "consent": True} for a in ids],
            **extra,
        },
        str(uuid4()),
    )


def drafts(c):
    return c.get("/api/drafts").json()


def test_batch_preserves_order_sources_and_saves_without_dates(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        v = ImageVision()
        tid = setup(c, h, v)
        ids = [upload(c, h, str(i)) for i in range(2)]
        response = batch(c, h, tid, ids)
        assert response.status_code == 200, response.text
        r = wait_run(c, response.json()["id"])
        assert r["data"]["status"] == "done", r
        assert len(r["data"]["job_ids"]) == 2 and v.calls == 2
        d = drafts(c)[0]
        p = d["data"]["payload"]
        assert p["asset_ids"] == ids
        assert [i["source_asset_id"] for i in p["items"]] == [
            ids[0],
            ids[0],
            ids[1],
            ids[1],
        ]
        assert all(i["due_at"] is None for i in p["items"])
        events = c.get("/api/agent/runs/" + r["id"] + "/events?after=0").text
        assert all(a in events for a in ids)
        assert (
            post(
                c,
                h,
                "/drafts/" + d["id"] + "/confirm",
                {"revision": d["revision"]},
                "save",
            ).status_code
            == 200
        )
        tasks = c.get("/api/tasks").json()
        assert len(tasks) == 4
        assert {t["data"]["asset_id"] for t in tasks} == set(ids)
        assert all(t["data"]["due_at"] is None for t in tasks)


class PartialFailure(ImageVision):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def extract_assignments(self, *args):
        self.attempts += 1
        if self.attempts == 2:
            raise TimeoutError("synthetic only")
        return await super().extract_assignments(*args)


def test_failure_caches_success_and_does_not_leave_phantom_busy_jobs(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        v = PartialFailure()
        tid = setup(c, h, v)
        ids = [upload(c, h, str(i)) for i in range(3)]
        r = wait_run(c, batch(c, h, tid, ids).json()["id"])
        assert r["data"]["status"] == "failed"
        assert not drafts(c)
        jobs = [c.get("/api/jobs/" + jid).json() for jid in r["data"]["job_ids"]]
        assert [j["data"]["status"] for j in jobs] == ["done", "failed", "failed"]
        assert jobs[0]["data"]["extracted_payload"]
        response = post(
            c,
            h,
            "/agent/runs/" + r["id"] + "/image/retry",
            {"revision": r["revision"]},
            "retry",
        )
        assert response.status_code == 200, response.text
        r = wait_run(c, r["id"])
        assert r["data"]["status"] == "done"
        assert v.attempts == 4 and len(drafts(c)) == 1
        d = drafts(c)[0]
        assert len(d["data"]["payload"]["items"]) == 6
        assert len({d["id"]}) == 1


def test_defer_is_revision_checked_optional_and_durable(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        v = ImageVision()
        tid = setup(c, h, v)
        aid = upload(c, h)
        r = wait_run(c, batch(c, h, tid, [aid]).json()["id"])
        assert r["data"]["status"] == "done"
        d = drafts(c)[0]
        url = "/agent/assignment-drafts/" + d["id"] + "/defer-deadlines"
        assert (
            post(c, h, url, {"revision": d["revision"] + 1}, "stale").status_code == 409
        )
        a = post(c, h, url, {"revision": d["revision"]}, "defer")
        assert a.status_code == 200, a.text
        assert post(c, h, url, {"revision": d["revision"]}, "defer").json() == a.json()
        changed = drafts(c)[0]
        assert changed["data"]["source"]["deadline_followup"] == "deferred"
        assert all(i["due_at"] is None for i in changed["data"]["payload"]["items"])
        assert (
            post(
                c,
                h,
                "/drafts/" + d["id"] + "/confirm",
                {"revision": changed["revision"]},
                "save",
            ).status_code
            == 200
        )
        assert all(t["data"]["due_at"] is None for t in c.get("/api/tasks").json())


def test_batch_contract_rejects_duplicates_mixed_false_consent_and_foreign_assets(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        tid = setup(c, h, ImageVision())
        aid = upload(c, h)
        assert batch(c, h, tid, [aid, aid]).status_code == 422
        assert batch(c, h, tid, [aid] * 6).status_code == 422
        assert (
            batch(
                c, h, tid, [aid], attachment={"asset_id": aid, "consent": True}
            ).status_code
            == 422
        )
        assert (
            post(
                c,
                h,
                "/agent/runs",
                {
                    "thread_id": tid,
                    "attachments": [{"asset_id": aid, "consent": False}],
                },
                "consent",
            ).status_code
            == 422
        )
        c.post("/api/auth/logout", headers=h)
        bob = register_login(c, "bob@example.com")
        tid = post(c, bob, "/agent/threads", {}, "bob-thread").json()["id"]
        assert batch(c, bob, tid, [aid]).status_code == 404


def test_source_mapping_cannot_be_retargeted_by_review_edits(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        tid = setup(c, h, ImageVision())
        ids = [upload(c, h, str(i)) for i in range(2)]
        r = wait_run(c, batch(c, h, tid, ids).json()["id"])
        assert r["data"]["status"] == "done"
        d = drafts(c)[0]
        p = d["data"]["payload"]
        p["items"][0]["source_asset_id"] = ids[1]
        response = c.put(
            "/api/drafts/" + d["id"],
            json={"revision": d["revision"], "payload": p},
            headers={**h, "Idempotency-Key": "retarget"},
        )
        assert response.status_code == 422
        assert drafts(c)[0]["data"]["payload"]["items"][0]["source_asset_id"] == ids[0]


def test_original_user_skip_text_defers_followup_without_changing_dates(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        tid = setup(c, h, ImageVision())
        aid = upload(c, h)
        r = wait_run(c, batch(c, h, tid, [aid]).json()["id"])
        assert r["data"]["status"] == "done"
        run = post(
            c,
            h,
            "/agent/runs",
            {"thread_id": tid, "message": "日期暂不填写"},
            "skip-text",
        )
        wait_run(c, run.json()["id"])
        d = drafts(c)[0]
        assert d["data"]["source"]["deadline_followup"] == "deferred"
        assert all(i["due_at"] is None for i in d["data"]["payload"]["items"])


def test_restart_retries_only_unfinished_batch_images(tmp_path):
    from tests.test_chat_images import ImageModel

    with make_client(tmp_path) as c:
        h = register_login(c)
        cookies = dict(c.cookies)
        tid = setup(c, h, PartialFailure())
        ids = [upload(c, h, str(i)) for i in range(3)]
        r = wait_run(c, batch(c, h, tid, ids).json()["id"])
        assert r["data"]["status"] == "failed"
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        v = ImageVision()
        c.app.state.gateway = v
        c.app.state.agent_model_factory = lambda: ImageModel()
        latest = c.get("/api/agent/runs/" + r["id"]).json()
        response = post(
            c,
            h,
            "/agent/runs/" + r["id"] + "/image/retry",
            {"revision": latest["revision"]},
            "restart-retry",
        )
        assert response.status_code == 200, response.text
        assert wait_run(c, r["id"])["data"]["status"] == "done"
        assert v.calls == 2
        assert len(drafts(c)) == 1
        assert len(drafts(c)[0]["data"]["payload"]["items"]) == 6


def test_cancel_batch_keeps_no_busy_jobs_or_actionable_draft(tmp_path):
    import asyncio
    import threading

    class GateSecond(ImageVision):
        def __init__(self):
            super().__init__()
            self.attempts = 0
            self.release = threading.Event()

        async def extract_assignments(self, *args):
            self.attempts += 1
            if self.attempts == 2:
                while not self.release.is_set():
                    await asyncio.sleep(0.01)
            return await super().extract_assignments(*args)

    with make_client(tmp_path) as c:
        h = register_login(c)
        v = GateSecond()
        tid = setup(c, h, v)
        ids = [upload(c, h, str(i)) for i in range(3)]
        response = batch(c, h, tid, ids).json()
        for _ in range(100):
            job = c.get("/api/jobs/" + response["data"]["job_ids"][1]).json()
            if job["data"]["status"] == "running":
                break
            time.sleep(0.02)
        else:
            raise AssertionError("Second image did not start")
        run = c.get("/api/agent/runs/" + response["id"]).json()
        stopped = post(
            c,
            h,
            "/agent/runs/" + run["id"] + "/image/cancel",
            {"revision": run["revision"]},
            "stop",
        )
        assert stopped.status_code == 200, stopped.text
        v.release.set()
        assert not drafts(c)
        statuses = [
            c.get("/api/jobs/" + jid).json()["data"]["status"]
            for jid in response["data"]["job_ids"]
        ]
        assert statuses == ["done", "cancelled", "cancelled"]
