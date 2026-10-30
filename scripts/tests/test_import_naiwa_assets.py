import hashlib
import json
import runpy
import subprocess
from pathlib import Path

import pytest
from PIL import Image

MODULE = Path(__file__).resolve().parents[1] / "import-naiwa-assets.py"
REF = "008eb12636f517aedecee6f1a1fc773c2f0df6c4"
IMPORTER = runpy.run_path(str(MODULE))


def fixture(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    def png(relative, size=(420, 560)):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", size, (20, 80, 160, 128)).save(path)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    idle_hash = png("embedded/body/idle_000.png")
    png("embedded/body/idle_001.png")
    (source / "embedded/runtime.json").write_text(json.dumps({"canvas": {"width": 420, "height": 560}, "body_dir": "body", "clips": {"idle": {"frames": 2, "duration_ns": 85000000}}, "frames_sha256": {f"body/idle_{i:03}.png": idle_hash for i in range(2)}}))
    pose_hash = png("pose/0000.png")
    (source / "pose/manifest.json").write_text(json.dumps({"canvas": {"width": 420, "height": 560}, "groundY": 540, "fps": 24, "frameCount": 1, "loop": True, "frames": [{"file": "0000.png", "sha256": pose_hash}]}))
    icon_hash = png("icon.png", (256, 256))
    selection = {"upstream_ref": REF, "repository": "https://github.com/SbongeBobybl/NaiWaChatPet", "rights": {"status": "verified", "basis": "Synthetic fixture generated for tests; no third-party art."}, "canvas": {"width": 420, "height": 560}, "ground_y": 540,
                 "icon": {"source": "icon.png", "sha256": icon_hash},
                 "clips": {"idle": {"runtime": "embedded/runtime.json", "runtime_clip": "idle"}, "pose": {"manifest": "pose/manifest.json", "pose_hold_ms": 800}},
                 "states": {state: "idle" if state == "idle" else "pose" for state in ["starting", "idle", "thinking", "replying", "approval", "error", "sleeping"]},
                 "actions": [{"id": "greet", "title": "打招呼", "clips": ["pose"], "hold_ms": 800}]}
    return source, selection


def import_pack(source, selection, output, ref=REF):
    return IMPORTER["import_asset_pack"](source, selection, output, source_ref=ref)


def test_import_keeps_source_bytes_timing_non_square_canvas_and_provenance(tmp_path):
    source, selection = fixture(tmp_path)
    output = tmp_path / "pack"
    result = import_pack(source, selection, output)
    assert result["canvas"] == {"width": 420, "height": 560}
    assert len(result["clips"]["idle"]["frames"]) == 2
    assert result["clips"]["idle"]["frames"][0]["duration_ns"] == 85000000
    assert result["clips"]["pose"]["frames"][0]["duration_ns"] == round(1000000000 / 24)
    assert result["clips"]["pose"]["source_fps"] == 24
    assert result["clips"]["pose"]["pose_hold_ms"] == 800
    frame = result["clips"]["idle"]["frames"][0]
    assert (output / frame["file"]).read_bytes() == (source / "embedded/body/idle_000.png").read_bytes()
    assert frame["source_path"] == "embedded/body/idle_000.png"
    assert (output / result["default_frame"]).is_file()
    assert json.loads((output / "asset-pack.json").read_text())["upstream_ref"] == REF


@pytest.mark.parametrize("failure", ["hash", "canvas", "missing", "escape", "symlink", "fps", "rights", "ref", "state"])
def test_failed_import_keeps_the_existing_pack_intact(tmp_path, failure):
    source, selection = fixture(tmp_path)
    output = tmp_path / "pack"
    output.mkdir()
    (output / "sentinel.txt").write_text("original pack")
    ref = REF
    manifest = source / "pose/manifest.json"
    data = json.loads(manifest.read_text())
    if failure == "hash": data["frames"][0]["sha256"] = "0" * 64
    elif failure == "canvas": data["canvas"]["width"] = 320
    elif failure == "missing": (source / "pose/0000.png").unlink()
    elif failure == "escape": data["frames"][0]["file"] = "../../outside.png"
    elif failure == "symlink":
        original = source / "pose/0000.png"
        target = tmp_path / "outside.png"
        original.rename(target)
        original.symlink_to(target)
    elif failure == "fps": data["fps"] = 0
    elif failure == "rights": selection["rights"]["status"] = "pending"
    elif failure == "ref": ref = "f" * 40
    elif failure == "state": selection["states"]["idle"] = "missing-clip"
    manifest.write_text(json.dumps(data))
    with pytest.raises((ValueError, FileNotFoundError)):
        import_pack(source, selection, output, ref)
    assert sorted(path.name for path in output.iterdir()) == ["sentinel.txt"]
    assert (output / "sentinel.txt").read_text() == "original pack"


def test_source_checkout_cannot_be_modified_by_output_selection(tmp_path):
    source, selection = fixture(tmp_path)
    with pytest.raises(ValueError):
        import_pack(source, selection, source / "generated")


def test_checkout_revision_alone_does_not_authorize_modified_source_files(tmp_path):
    source = tmp_path / 'git-source'
    source.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.DEVNULL, text=True).strip()
    git('init', '-q')
    path = source / 'manifest.json'
    path.write_text('{}')
    git('add', 'manifest.json')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'synthetic source')
    ref = git('rev-parse', 'HEAD')
    assert IMPORTER['verify_checkout'](source, expected_ref=ref) == ref
    path.write_text('{"modified": true}')
    with pytest.raises(ValueError):
        IMPORTER['verify_checkout'](source, expected_ref=ref)


def test_selected_manifest_checksum_must_match_the_bytes_parsed(tmp_path):
    source, selection = fixture(tmp_path)
    manifest = source / 'pose/manifest.json'
    selection['clips']['pose']['manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    body = json.loads(manifest.read_text())
    body['fps'] = 30
    manifest.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        import_pack(source, selection, tmp_path / 'pack')
