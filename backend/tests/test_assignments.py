from io import BytesIO

from PIL import Image

from tests.test_foundation import make_client, register_login


class FakeVision:
    async def extract_assignments(self, *args, **kwargs):
        return {
            "items": [
                {
                    "title": "数学练习",
                    "requirements": ["第 2 章"],
                    "due_at": None,
                    "due_text": "下周五",
                    "uncertain_fields": ["due_at"],
                    "evidence": [{"field": "title", "text": "数学练习"}],
                },
                {
                    "title": "实验报告",
                    "requirements": ["提交 PDF"],
                    "due_at": None,
                    "uncertain_fields": ["due_at"],
                },
            ],
            "warnings": [],
        }


def png():
    b = BytesIO()
    Image.new("RGB", (20, 20)).save(b, format="PNG")
    return b.getvalue()


def test_multi_assignment_private_asset_and_confirmation(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.gateway = FakeVision()
        asset = c.post(
            "/api/assets",
            files={"file": ("a.png", png(), "image/png")},
            headers={**h, "Idempotency-Key": "upload"},
        )
        assert asset.status_code == 200
        a = asset.json()
        job = c.post(
            "/api/assignment-jobs",
            json={"asset_id": a["id"], "consent": True},
            headers={**h, "Idempotency-Key": "recognize"},
        ).json()
        job = c.get("/api/jobs/" + job["id"]).json()
        assert job["data"]["status"] == "done"
        assert c.get("/api/tasks").json() == []
        d = c.get("/api/drafts/" + job["data"]["draft_id"]).json()
        assert len(d["data"]["payload"]["items"]) == 2
        assert all(x["due_at"] is None for x in d["data"]["payload"]["items"])
        url = f"/api/drafts/{d['id']}/confirm"
        for key in ["confirm", "twice"]:
            assert (
                c.post(
                    url, json={"revision": 1}, headers={**h, "Idempotency-Key": key}
                ).status_code
                == 200
            )
        assert len(c.get("/api/tasks").json()) == 2
        c.post("/api/auth/logout", headers=h)
        h = register_login(c, "bob@example.com")
        assert c.get("/api/assets/" + a["id"]).status_code == 404
        assert c.get("/api/jobs/" + job["id"]).status_code == 404


def test_upload_validation_and_missing_model_failure(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        for raw in [b"not png", b"x" * (10 * 1024 * 1024 + 1)]:
            assert c.post(
                "/api/assets",
                files={"file": ("a.png", raw, "image/png")},
                headers={**h, "Idempotency-Key": "bad-" + str(len(raw))},
            ).status_code in (413, 422)
        a = c.post(
            "/api/assets",
            files={"file": ("a.png", png(), "image/png")},
            headers={**h, "Idempotency-Key": "upload"},
        ).json()
        job = c.post(
            "/api/assignment-jobs",
            json={"asset_id": a["id"], "consent": True},
            headers={**h, "Idempotency-Key": "job"},
        ).json()
        assert c.get("/api/jobs/" + job["id"]).json()["data"]["status"] == "failed"
        assert c.get("/api/tasks").json() == []


def test_model_course_injection_and_relative_date():
    import pytest

    from app.model_gateway import normalize_extraction

    with pytest.raises(ValueError):
        normalize_extraction(
            {
                "items": [
                    {"title": "x", "requirements": [], "course_id": "someone-else"}
                ]
            },
            [],
            None,
        )
    got = normalize_extraction(
        {
            "items": [
                {
                    "title": "x",
                    "requirements": [],
                    "due_text": "下周五",
                    "due_at": "2026-10-23T23:59:00+08:00",
                }
            ]
        },
        [],
        None,
    )
    assert got["items"][0]["due_at"] is None
    assert "due_at" in got["items"][0]["uncertain_fields"]


def test_jpeg_webp_and_decoded_pixel_limit(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        for fmt, mime in [("JPEG", "image/jpeg"), ("WEBP", "image/webp")]:
            out = BytesIO()
            Image.new("RGB", (20, 20)).save(out, format=fmt)
            response = c.post(
                "/api/assets",
                files={"file": ("test." + fmt.lower(), out.getvalue(), mime)},
                headers={**h, "Idempotency-Key": fmt},
            )
            assert response.status_code == 200, response.text
            image = c.get("/api/assets/" + response.json()["id"])
            assert image.headers["content-type"] == "image/png"
        out = BytesIO()
        Image.new("RGB", (5000, 4001)).save(out, format="PNG")
        assert len(out.getvalue()) < 10 * 1024 * 1024
        response = c.post(
            "/api/assets",
            files={"file": ("pixel-limit.png", out.getvalue(), "image/png")},
            headers={**h, "Idempotency-Key": "pixels"},
        )
        assert response.status_code == 413
