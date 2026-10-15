from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    return TestClient(
        create_app(
            {
                "app_mode": "shared",
                "database_url": f"sqlite+aiosqlite:///{tmp_path}/test.db",
                "upload_dir": str(tmp_path / "uploads"),
                "agent_db_path": str(tmp_path / "agent.db"),
                "public_origin": "http://testserver",
                "secure_cookie": False,
                "model_api_key": "",
                "text_model": "",
                "vision_model": "",
                "scut_adapter_path": "",
            }
        )
    )


def register_login(client, email="alice@example.com"):
    csrf = client.get("/api/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf, "Origin": "http://testserver"}
    assert (
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "Student!Password2026"},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/auth/login",
            data={"username": email, "password": "Student!Password2026"},
            headers=headers,
        ).status_code
        == 204
    )
    return headers


def test_cookie_auth_and_owner_isolation(tmp_path):
    with make_client(tmp_path) as c:
        assert c.get("/api/settings").status_code == 401
        h = register_login(c)
        s = c.get("/api/settings").json()
        s["data"]["daily_limit_minutes"] = 90
        assert (
            c.put(
                "/api/settings", json=s, headers={**h, "Idempotency-Key": "settings-1"}
            ).status_code
            == 200
        )
        assert c.post("/api/auth/logout", headers=h).status_code == 204
        register_login(c, "bob@example.com")
        assert c.get("/api/settings").json()["data"]["daily_limit_minutes"] == 180


def test_csrf_revision_and_persistence(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        cookie = dict(c.cookies)
        s = c.get("/api/settings").json()
        assert c.put("/api/settings", json=s).status_code == 403
        s["data"]["daily_limit_minutes"] = 120
        r = c.put("/api/settings", json=s, headers={**h, "Idempotency-Key": "s1"})
        assert r.status_code == 200
        assert (
            c.put(
                "/api/settings", json=s, headers={**h, "Idempotency-Key": "s2"}
            ).status_code
            == 409
        )
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert c.get("/api/settings").json()["data"]["daily_limit_minutes"] == 120


def test_same_key_different_payload_conflicts(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        s = c.get("/api/settings").json()
        headers = {**h, "Idempotency-Key": "one"}
        assert c.put("/api/settings", json=s, headers=headers).status_code == 200
        assert c.put("/api/settings", json=s, headers=headers).status_code == 200
        s["data"]["daily_limit_minutes"] = 90
        assert c.put("/api/settings", json=s, headers=headers).status_code == 409
