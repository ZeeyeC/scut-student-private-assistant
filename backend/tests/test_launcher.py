"""Launcher pure logic: isolation, bundled resources and local-only identity."""

from pathlib import Path

import pytest

from app.launcher import (
    EXTENSION_OWNED_MARKER,
    ISOLATED_ACCEPTANCE_MARKER,
    desktop_config,
    extension_destination,
    launch_arguments,
    same_service,
    service_identity,
    stage_extension,
)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


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
    (source / "manifest.json").write_text('{"name":"Campus Companion","version":"1.0.0"}')
    (source / "background.js").write_text("/* test-only */")
    (tmp_path / "resources" / ".env").write_text("SECRET=do-not-copy")
    personal = tmp_path / "personal"
    dest = stage_extension(tmp_path / "resources", personal)
    assert dest == extension_destination(personal)
    assert (dest / "background.js").is_file()
    assert (dest / EXTENSION_OWNED_MARKER).is_file()
    assert not (dest / ".env").exists()
    (source / "background.js").write_text("/* updated */")
    assert stage_extension(tmp_path / "resources", personal) == dest
    assert (dest / "background.js").read_text() == "/* updated */"


def test_extension_destination_macos_nonmacos_isolated_and_config_alignment(
    tmp_path, isolated_home, monkeypatch
):
    import app.launcher as launcher

    resources = tmp_path / "resources"
    source = resources / "extension" / ".output" / "chrome-mv3"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text('{"name":"Campus Companion","version":"1.0.0"}')
    root = tmp_path / "user-data"
    root.mkdir()

    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    expected_mac = isolated_home / "Documents" / "课间" / "浏览器扩展"
    assert extension_destination(root) == expected_mac
    mac_cfg = desktop_config(root, resources, project=False)
    staged_mac = stage_extension(resources, root)
    assert Path(mac_cfg.extension_dir) == expected_mac == staged_mac

    monkeypatch.setattr(launcher.sys, "platform", "linux")
    expected_nonmac = root / "desktop-extension"
    assert extension_destination(root) == expected_nonmac
    nonmac_cfg = desktop_config(root, resources, project=False)
    staged_nonmac = stage_extension(resources, root)
    assert Path(nonmac_cfg.extension_dir) == expected_nonmac == staged_nonmac

    # Directory with the marker name does not activate isolated mode; only a file does.
    (root / ISOLATED_ACCEPTANCE_MARKER).mkdir()
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    assert extension_destination(root) == expected_mac
    (root / ISOLATED_ACCEPTANCE_MARKER).rmdir()

    (root / ISOLATED_ACCEPTANCE_MARKER).write_text("isolated\n")
    expected_isolated = root / "Documents" / "课间" / "浏览器扩展"
    assert extension_destination(root) == expected_isolated
    iso_cfg = desktop_config(root, resources, project=False)
    staged_iso = stage_extension(resources, root)
    assert Path(iso_cfg.extension_dir) == expected_isolated == staged_iso


def test_stage_extension_preserves_legacy_and_unowned_siblings_and_upgrades_matching_manifest(
    tmp_path, isolated_home, monkeypatch
):
    import app.launcher as launcher

    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    resources = tmp_path / "resources"
    source = resources / "extension" / ".output" / "chrome-mv3"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text('{"name":"课间课表助手","version":"2.0.0"}')
    (source / "background.js").write_text("v2")

    root = tmp_path / "data"
    legacy = root / "desktop-extension"
    legacy.mkdir(parents=True)
    (legacy / "legacy.txt").write_text("keep-me")

    dest = extension_destination(root)
    dest.mkdir(parents=True)
    # Pre-existing legitimate version without owned marker but matching manifest name
    (dest / "manifest.json").write_text('{"name":"课间课表助手","version":"1.0.0"}')
    (dest / "old.js").write_text("v1")
    unowned_temp = dest.parent / ".extension-previous"
    unowned_temp.mkdir()
    (unowned_temp / "important.txt").write_text("do-not-delete")

    staged = stage_extension(resources, root)
    assert staged == dest
    assert (dest / "background.js").read_text() == "v2"
    assert not (dest / "old.js").exists()
    assert (dest / EXTENSION_OWNED_MARKER).is_file()
    assert (legacy / "legacy.txt").read_text() == "keep-me"
    assert (unowned_temp / "important.txt").read_text() == "do-not-delete"
    assert [
        p.name
        for p in dest.parent.iterdir()
        if p.name.startswith(f".{dest.name}-")
    ] == []


def test_stage_extension_rejects_symlinks_and_unrelated_preexisting_folders(
    tmp_path, isolated_home, monkeypatch
):
    import app.launcher as launcher

    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    resources = tmp_path / "resources"
    source = resources / "extension" / ".output" / "chrome-mv3"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text('{"name":"课间课表助手","version":"1.0.0"}')

    root = tmp_path / "data"
    root.mkdir()
    dest = extension_destination(root)
    dest.mkdir(parents=True)
    (dest / "notes.txt").write_text("user notes")

    with pytest.raises(RuntimeError, match="不属于本应用"):
        stage_extension(resources, root)
    assert (dest / "notes.txt").read_text() == "user notes"

    # Also reject a preexisting folder with a different manifest name
    (dest / "manifest.json").write_text('{"name":"Other Extension","version":"1.0.0"}')
    with pytest.raises(RuntimeError, match="不属于本应用"):
        stage_extension(resources, root)
    assert (dest / "notes.txt").read_text() == "user notes"

    # Also reject symlink destination without modifying target
    for child in list(dest.iterdir()):
        child.unlink()
    dest.rmdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("safe")
    dest.symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(RuntimeError, match="符号链接"):
        stage_extension(resources, root)
    assert dest.is_symlink()
    assert (elsewhere / "keep.txt").read_text() == "safe"


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


def test_reuse_keeps_database_identity_checks_even_with_pet_capabilities(tmp_path, monkeypatch):
    import app.launcher as launcher
    config = desktop_config(tmp_path, tmp_path, project=False)
    identity = service_identity(config)
    monkeypatch.setattr(launcher, "probe", lambda: {**identity, "capabilities": ["pet-state"]})
    assert same_service(config)
    monkeypatch.setattr(launcher, "probe", lambda: {**identity, "database_id": "other-profile", "capabilities": ["pet-state"]})
    with pytest.raises(RuntimeError, match="另一份资料"):
        same_service(config)


def test_health_advertises_pet_features(tmp_path):
    from tests.test_foundation import make_client
    with make_client(tmp_path) as c:
        response = c.get("/api/healthz")
        assert response.status_code == 200
        assert set(response.json().get("capabilities", [])) >= {"after-class-checkin", "calendar-course-entry", "pet-state"}


def test_command_line_start_never_opens_a_daily_browser(tmp_path, monkeypatch):
    from app import launcher

    calls = []
    monkeypatch.setattr(launcher, 'start', lambda root, resources, **options: calls.append(options))
    monkeypatch.setattr(launcher.sys, 'argv', ['CampusCompanion', '--data-dir', str(tmp_path)])
    assert launcher.main() == 0
    assert calls[0]['browser'] is False


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_failed_extension_install_preserves_previous_copy(tmp_path, monkeypatch, rollback_fails):
    resources = tmp_path / "resources"
    source = resources / "extension/.output/chrome-mv3"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text('{"name":"Campus Companion","version":"1"}')
    (source / "background.js").write_text("old")
    root = tmp_path / "data"
    destination = stage_extension(resources, root)
    (source / "background.js").write_text("new")
    original_rename = Path.rename

    def fail_install(path, target):
        if "-stage-" in path.name or (rollback_fails and "-backup-" in path.parent.name):
            raise OSError("simulated rename failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_install)
    with pytest.raises(OSError, match="simulated"):
        stage_extension(resources, root)
    if rollback_fails:
        copies = list(destination.parent.glob(f".{destination.name}-backup-*/{destination.name}/background.js"))
        assert len(copies) == 1 and copies[0].read_text() == "old"
    else:
        assert (destination / "background.js").read_text() == "old"
