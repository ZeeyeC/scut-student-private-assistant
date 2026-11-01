import sqlite3
from pathlib import Path

import pytest


def test_backup_restores_business_checkpoint_and_private_assets(tmp_path):
    from app.backup import backup, restore

    src = tmp_path / "src"
    src.mkdir()
    (src / "uploads").mkdir()
    (src / "uploads" / "a.png").write_bytes(b"private-test-image")
    for file, value in [("campus.db", "task-1"), ("agent.db", "pending-confirmation")]:
        with sqlite3.connect(src / file) as db:
            db.execute("create table facts (value text)")
            db.execute("insert into facts values (?)", (value,))
    package = tmp_path / "backup.zip"
    backup(src / "campus.db", src / "agent.db", src / "uploads", package)
    target = tmp_path / "restored"
    restore(package, target)
    for file, value in [("campus.db", "task-1"), ("agent.db", "pending-confirmation")]:
        with sqlite3.connect(target / file) as db:
            assert db.execute("select value from facts").fetchone()[0] == value
    assert (target / "uploads" / "a.png").read_bytes() == b"private-test-image"
    with pytest.raises(ValueError):
        restore(package, target)
    (src / "campus.db.server.lock").write_text("active")
    with pytest.raises(ValueError, match="停止"):
        backup(
            src / "campus.db", src / "agent.db", src / "uploads", tmp_path / "busy.zip"
        )


def test_delete_own_data_removes_assets_threads_but_keeps_other_owner(tmp_path):
    from tests.test_assignments import png
    from tests.test_foundation import make_client, register_login

    with make_client(tmp_path) as c:
        h = register_login(c)
        a = c.post(
            "/api/assets",
            files={"file": ("a.png", png(), "image/png")},
            headers={**h, "Idempotency-Key": "upload"},
        ).json()
        c.post("/api/auth/logout", headers=h)
        h2 = register_login(c, "bob@example.com")
        c.post(
            "/api/agent/threads", json={}, headers={**h2, "Idempotency-Key": "thread"}
        )
        c.post("/api/auth/logout", headers=h2)
        c.post(
            "/api/auth/login",
            data={"username": "alice@example.com", "password": "Student!Password2026"},
            headers=h2,
        )
        export = c.get("/api/data-export")
        assert export.status_code == 200
        assert "resources" in export.json()
        assert (
            c.post(
                "/api/data-delete",
                json={"confirmation": "删除我的所有数据"},
                headers={**h2, "Idempotency-Key": "delete"},
            ).status_code
            == 200
        )
        assert not Path(c.app.state.config.upload_dir, a["data"]["filename"]).exists()
        assert c.get("/api/assets/" + a["id"]).status_code == 404
        c.post("/api/auth/logout", headers=h2)
        c.post(
            "/api/auth/login",
            data={"username": "bob@example.com", "password": "Student!Password2026"},
            headers=h2,
        )
        assert len(c.get("/api/agent/threads").json()) == 1
        assert c.get("/api/no-such-api").status_code == 404
        assert (
            c.get("/api/no-such-api")
            .headers["content-type"]
            .startswith("application/json")
        )


def test_backup_preserves_nested_knowledge_originals(tmp_path):
    from app.backup import backup, restore
    from uuid import uuid4

    src = tmp_path / "src"
    src.mkdir()
    uploads = src / "uploads"
    uploads.mkdir()
    owner = str(uuid4())
    relative = Path("knowledge") / owner / (str(uuid4()) + ".docx")
    (uploads / relative).parent.mkdir(parents=True)
    (uploads / relative).write_bytes(b"synthetic-original")
    for name in ("campus.db", "agent.db"):
        with sqlite3.connect(src / name) as db:
            db.execute("create table facts(value text)")
    package = tmp_path / "backup.zip"
    backup(src / "campus.db", src / "agent.db", uploads, package)
    restore(package, tmp_path / "restored")
    assert (
        tmp_path / "restored/uploads" / relative
    ).read_bytes() == b"synthetic-original"
