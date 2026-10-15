"""Launcher pure logic: isolation, bundled resources and local-only identity."""

from pathlib import Path

import pytest

from app.launcher import (
    desktop_config,
    launch_arguments,
    service_identity,
    stage_extension,
)


def test_packaged_defaults_are_separate_from_checkout_and_ignore_ambient_env(
    tmp_path, monkeypatch
):
    resources = tmp_path / "bundle"
    resources.mkdir()
    root = tmp_path / "personal"
    root.mkdir()
    monkeypatch.setenv("APP_MODE", "shared")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///do-not-use.db")
    config = desktop_config(root, resources, project=False)
    assert config.app_mode == "local"
    assert config.public_origin == "http://127.0.0.1:5173"
    assert Path(config.database_url.split("///", 1)[1]) == root / "data" / "campus.db"
    assert config.settings_file == str(root / "model.env")
    assert not config.model_api_key
    assert service_identity(config) == service_identity(config)
    other = desktop_config(tmp_path / "other", resources, project=False)
    assert service_identity(config) != service_identity(other)


def test_source_configuration_preserves_existing_key_and_database(tmp_path):
    (tmp_path / ".env").write_text(
        "MODEL_API_KEY='test-secret'\nTEXT_MODEL=test-model\nDATABASE_URL=sqlite+aiosqlite:///./custom.db\n"
    )
    config = desktop_config(tmp_path, tmp_path, project=True)
    assert config.model_api_key == "test-secret"
    assert config.text_model == "test-model"
    assert config.database_url == f"sqlite+aiosqlite:///{tmp_path}/custom.db"
    assert config.settings_file == str(tmp_path / ".env")
    assert service_identity(config)["application"] == "campus-companion"


def test_extension_stage_is_stable_and_does_not_copy_private_config(tmp_path):
    source = tmp_path / "resources" / "extension" / ".output" / "chrome-mv3"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text('{"version":"1.0.0"}')
    (source / "background.js").write_text("/* test-only */")
    (tmp_path / "resources" / ".env").write_text("SECRET=do-not-copy")
    dest = stage_extension(tmp_path / "resources", tmp_path / "personal")
    assert dest == tmp_path / "personal" / "desktop-extension"
    assert (dest / "background.js").is_file()
    assert not (dest / ".env").exists()
    (source / "background.js").write_text("/* updated */")
    assert stage_extension(tmp_path / "resources", tmp_path / "personal") == dest
    assert (dest / "background.js").read_text() == "/* updated */"


def test_child_arguments_fixed_and_invalid_sqlite_path_rejected(tmp_path):
    command = launch_arguments(tmp_path, project=True, frozen=False)
    assert command[-3:] == ["--data-dir", str(tmp_path), "--project"]
    assert "--serve" in command
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://example/db\n")
    with pytest.raises(ValueError, match="SQLite"):
        desktop_config(tmp_path, tmp_path, project=True)


def test_source_launch_never_replaces_extension_source_tree(tmp_path):
    source = tmp_path / "extension"
    built = source / ".output" / "chrome-mv3"
    built.mkdir(parents=True)
    (source / "wxt.config.ts").write_text("// source must survive")
    (built / "manifest.json").write_text('{"version":"1.0.0"}')
    result = stage_extension(tmp_path, tmp_path)
    assert (source / "wxt.config.ts").is_file()
    assert result != source
