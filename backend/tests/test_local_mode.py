import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_foundation import make_client, register_login

ORIGIN = "http://127.0.0.1:5173"


def local_client(root, **changes):
    config = {
        "app_mode": "local",
        "database_url": f"sqlite+aiosqlite:///{root}/test.db",
        "agent_db_path": str(root / "agent.db"),
        "upload_dir": str(root / "uploads"),
        "public_origin": ORIGIN,
        "model_api_key": "",
        "text_model": "",
        "vision_model": "",
        "scut_adapter_path": "",
        "settings_file": str(root / "local.env"),
    }
    config.update(changes)
    return TestClient(create_app(config), base_url=ORIGIN, client=("127.0.0.1", 12345))


def headers(client):
    token = client.get("/api/csrf").json()["csrf_token"]
    return {"Origin": ORIGIN, "X-CSRF-Token": token}


def test_local_automatic_profile_cookie_and_restart(tmp_path):
    with local_client(tmp_path) as c:
        assert c.get("/api/app-mode").json()["mode"] == "local"
        assert c.get("/api/me").status_code == 401
        assert c.post("/api/local/session", json={}).status_code == 403
        h = headers(c)
        for _ in range(2):
            assert c.post("/api/local/session", json={}, headers=h).status_code == 204
        owner = c.get("/api/me").json()["id"]
        s = c.get("/api/settings").json()
        s["data"]["daily_limit_minutes"] = 95
        assert (
            c.put(
                "/api/settings", json=s, headers={**h, "Idempotency-Key": "save"}
            ).status_code
            == 200
        )
        assert c.post("/api/auth/register", json={}, headers=h).status_code == 404
        assert c.get("/api/local/status").json()["selected"] is True
    with local_client(tmp_path) as c:
        assert (
            c.post("/api/local/session", json={}, headers=headers(c)).status_code == 204
        )
        assert c.get("/api/me").json()["id"] == owner
        assert c.get("/api/settings").json()["data"]["daily_limit_minutes"] == 95


def test_existing_profiles_require_explicit_choice_and_preserve_data(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        old_owner = c.get("/api/me").json()["id"]
        s = c.get("/api/settings").json()
        s["data"]["daily_limit_minutes"] = 75
        assert (
            c.put(
                "/api/settings", json=s, headers={**h, "Idempotency-Key": "old"}
            ).status_code
            == 200
        )
    with local_client(tmp_path) as c:
        info = c.get("/api/local/status").json()
        assert info["needs_selection"] and info["profiles"][0]["id"] == old_owner
        h = headers(c)
        assert c.post("/api/local/session", json={}, headers=h).status_code == 409
        assert (
            c.post(
                "/api/local/session", json={"profile_id": old_owner}, headers=h
            ).status_code
            == 204
        )
        assert c.get("/api/settings").json()["data"]["daily_limit_minutes"] == 75
        assert (
            c.post(
                "/api/local/session", json={"create_new": True}, headers=h
            ).status_code
            == 409
        )


def test_local_host_origin_peer_and_profile_capability(tmp_path):
    with local_client(tmp_path) as c:
        assert (
            c.get("/api/local/status", headers={"Host": "attacker.example"}).status_code
            == 403
        )
        assert (
            c.get(
                "/api/local/status", headers={"Origin": "https://attacker.example"}
            ).status_code
            == 403
        )
        h = headers(c)
        assert (
            c.post(
                "/api/local/session",
                json={"profile_id": "00000000-0000-0000-0000-000000000000"},
                headers=h,
            ).status_code
            == 404
        )
    root = tmp_path / "remote"
    root.mkdir()
    with TestClient(
        local_client(root).app, base_url=ORIGIN, client=("192.168.1.10", 1234)
    ) as c:
        assert c.get("/api/local/status").status_code == 403


def test_shared_mode_has_no_local_backdoor(tmp_path):
    with make_client(tmp_path) as c:
        assert c.get("/api/app-mode").json()["mode"] == "shared"
        assert c.post(
            "/api/local/session", json={}, headers={"Origin": "http://testserver"}
        ).status_code in {403, 404}
        assert c.get("/api/me").status_code == 401


def test_local_model_settings_private_and_installation_info(tmp_path):
    extension = tmp_path / "extension"
    extension.mkdir()
    (extension / "manifest.json").write_text('{"version":"1.0.0"}')
    with local_client(tmp_path, extension_dir=str(extension)) as c:
        assert c.get("/api/local/model-settings").status_code == 401
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)
        payload = {
            "revision": c.get("/api/local/model-settings").json()["revision"],
            "text_model": "openai/gpt-6-luna",
            "vision_model": "openai/gpt-6-luna",
            "model_base_url": "https://openrouter.ai/api/v1",
            "model_api_key": "test-secret-not-real",
        }
        r = c.put(
            "/api/local/model-settings",
            json=payload,
            headers={**h, "Idempotency-Key": "models-first"},
        )
        assert r.status_code == 200
        assert r.json()["key_configured"]
        assert "test-secret-not-real" not in r.text
        assert "test-secret-not-real" not in c.get("/api/local/model-settings").text
        payload["model_api_key"] = ""
        payload["revision"] = r.json()["revision"]
        assert c.put(
            "/api/local/model-settings",
            json=payload,
            headers={**h, "Idempotency-Key": "models-keep"},
        ).json()["key_configured"]
        assert "test-secret-not-real" in Path(tmp_path / "local.env").read_text()
        info = c.get("/api/local/extension-installation").json()
        assert info["available"] and info["directory"] == str(extension)
        assert (
            c.post(
                "/api/local/open-extension-folder", json={"path": "/"}, headers=h
            ).status_code
            == 422
        )


def test_model_validation_never_echoes_typed_key(tmp_path):
    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)
        result = c.put(
            "/api/local/model-settings",
            headers={**h, "Idempotency-Key": "invalid"},
            json={
                "revision": c.get("/api/local/model-settings").json()["revision"],
                "text_model": "model",
                "vision_model": "model",
                "model_base_url": "http://provider.example/v1",
                "model_api_key": "synthetic-private-secret",
            },
        )
        assert result.status_code == 422
        assert "synthetic-private-secret" not in result.text


def test_model_settings_replay_and_stale_form_do_not_overwrite(tmp_path):
    with local_client(tmp_path) as c:
        h = headers(c)
        c.post("/api/local/session", json={}, headers=h)
        previous = c.get("/api/local/model-settings").json()
        body = {k: v for k, v in previous.items() if k != "key_configured"}
        body.update(
            text_model="new-model",
            vision_model="new-vision",
            model_api_key="test-only",
            model_base_url="https://openrouter.ai/api/v1",
        )
        result = c.put(
            "/api/local/model-settings",
            json=body,
            headers={**h, "Idempotency-Key": "model-save"},
        )
        assert result.status_code == 200
        assert result.json().get("revision") != previous.get("revision")
        repeated = c.put(
            "/api/local/model-settings",
            json=body,
            headers={**h, "Idempotency-Key": "model-save"},
        )
        assert repeated.json() == result.json()
        body["text_model"] = "stale-overwrite"
        assert (
            c.put(
                "/api/local/model-settings",
                json=body,
                headers={**h, "Idempotency-Key": "another-tab"},
            ).status_code
            == 409
        )
        assert c.get("/api/local/model-settings").json()["text_model"] == "new-model"


def test_shutdown_requires_session_csrf_and_idle_launcher_service(tmp_path):
    with local_client(tmp_path) as c:
        h = headers(c)
        assert c.post("/api/local/shutdown", json={}, headers=h).status_code == 401
        c.post("/api/local/session", json={}, headers=h)
        assert c.post("/api/local/shutdown", json={}).status_code == 403
        terminal = c.post("/api/local/shutdown", json={}, headers=h)
        assert terminal.status_code == 409 and "终端" in terminal.text
        stopped = []
        c.app.state.request_shutdown = lambda: stopped.append(True)
        marker = object()
        c.app.state.running_tasks.add(marker)
        busy = c.post("/api/local/shutdown", json={}, headers=h)
        c.app.state.running_tasks.remove(marker)
        assert busy.status_code == 409 and "处理" in busy.text
        assert stopped == []
        assert c.post("/api/local/shutdown", json={}, headers=h).json() == {"stopping": True}
        for _ in range(20):
            if stopped:
                break
            time.sleep(0.05)
        assert stopped == [True]
