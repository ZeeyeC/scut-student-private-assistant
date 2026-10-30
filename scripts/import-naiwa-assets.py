"""Import selected, explicitly cleared PNG assets from a pinned read-only checkout."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

from PIL import Image

PIN = "008eb12636f517aedecee6f1a1fc773c2f0df6c4"
STATES = {"starting", "idle", "thinking", "replying", "approval", "error", "sleeping"}


def verify_checkout(source, *, expected_ref=PIN):
    command = ["git", "-C", str(source)]
    ref = subprocess.check_output(command + ["rev-parse", "HEAD"], text=True).strip()
    if ref != expected_ref:
        raise ValueError("Unexpected upstream revision")
    changed = subprocess.run(command + ["diff", "--quiet", "HEAD", "--"], check=False).returncode
    untracked = subprocess.check_output(command + ["ls-files", "--others", "--exclude-standard", "-z"])
    if changed or untracked:
        raise ValueError("Source checkout must be clean and read-only")
    return ref


def source_file(root, relative):
    if not isinstance(relative, str) or "\0" in relative:
        raise ValueError("Invalid source path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative or not parts.parts:
        raise ValueError("Source path escapes checkout")
    path = root
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Linked source file is not allowed")
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise FileNotFoundError("Selected source file is missing")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Selected file exceeds size limit")
    return path


def read_json(root, path, expected_hash=None):
    raw = source_file(root, path).read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("Manifest exceeds size limit")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_hash is not None and digest != expected_hash:
        raise ValueError("Source manifest hash mismatch")
    return json.loads(raw), digest


def verified_png(root, relative, declared_hash, size):
    raw = source_file(root, relative).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(declared_hash, str) or digest != declared_hash:
        raise ValueError("PNG hash does not match source manifest")
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.size != size:
            raise ValueError("PNG canvas does not match declaration")
        if "A" not in image.getbands() and "transparency" not in image.info:
            raise ValueError("PNG has no alpha channel")
        image.load()
    return raw, digest


def import_asset_pack(source, selection, output, *, source_ref):
    source, output = Path(source).resolve(), Path(output).absolute()
    if source_ref != PIN or selection.get("upstream_ref") != PIN:
        raise ValueError("Unexpected upstream revision")
    rights = selection.get("rights", {})
    if rights.get("status") != "verified" or not str(rights.get("basis", "")).strip():
        raise ValueError("Asset permission evidence must be explicit before import")
    if output.is_symlink() or output.resolve().is_relative_to(source):
        raise ValueError("Output must not modify the source checkout")
    canvas = selection.get("canvas")
    if canvas != {"width": 420, "height": 560}:
        raise ValueError("Expected original 420x560 canvas")
    ground = selection.get("ground_y")
    if not isinstance(ground, (int, float)) or not 0 <= ground <= 560:
        raise ValueError("Invalid ground line")
    payloads, clips = {}, {}
    for name, spec in selection.get("clips", {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", name):
            raise ValueError("Invalid clip identifier")
        if "manifest" in spec:
            document, manifest_hash = read_json(source, spec["manifest"], spec.get("manifest_sha256"))
            if document.get("canvas") != canvas:
                raise ValueError("Clip canvas differs from the pack")
            fps = document.get("fps")
            if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not 0 < fps <= 60:
                raise ValueError("Invalid source fps")
            duration = round(1000000000 / fps)
            entries = document.get("frames", [])
            if document.get("frameCount") != len(entries):
                raise ValueError("Frame count mismatch")
            directory = PurePosixPath(spec["manifest"]).parent
            sources = [(str(directory / entry["file"]), entry["sha256"]) for entry in entries]
            loop = document.get("loop", False)
            clip = {"source_manifest": spec["manifest"], "source_manifest_sha256": manifest_hash, "source_fps": fps,
                    "loop": loop, "ground_y": document.get("groundY", ground),
                    "transition_in": document.get("transitionIn", ""), "transition_out": document.get("transitionOut", "")}
        elif "runtime" in spec and spec.get("runtime_clip") == "idle":
            document, manifest_hash = read_json(source, spec["runtime"], spec.get("runtime_sha256"))
            if document.get("canvas") != canvas:
                raise ValueError("Runtime canvas differs from the pack")
            runtime = document["clips"]["idle"]
            duration = runtime["duration_ns"]
            directory = PurePosixPath(spec["runtime"]).parent
            paths = [str(PurePosixPath(document["body_dir"]) / f"idle_{i:03}.png") for i in range(runtime["frames"])]
            sources = [(str(directory / path), document["frames_sha256"][path]) for path in paths]
            clip = {"source_manifest": spec["runtime"], "source_manifest_sha256": manifest_hash, "source_duration_ns": duration,
                    "loop": True, "ground_y": ground, "transition_in": "", "transition_out": ""}
        else:
            raise ValueError("Unknown source clip format")
        if not 1 <= len(sources) <= 240 or isinstance(duration, bool) or not isinstance(duration, int) or not 0 < duration <= 10000000000:
            raise ValueError("Invalid frame count or duration")
        if not isinstance(clip["loop"], bool) or not 0 <= clip["ground_y"] <= 560:
            raise ValueError("Invalid loop or ground line")
        hold = spec.get("pose_hold_ms")
        if hold is not None:
            if len(sources) != 1 or hold != 800:
                raise ValueError("Manual pose must hold one frame for 800ms")
            clip["pose_hold_ms"] = hold
        frames = []
        for relative, digest in sources:
            raw, digest = verified_png(source, relative, digest, (420, 560))
            target = "frames/" + digest + ".png"
            payloads[target] = raw
            frames.append({"file": target, "sha256": digest, "duration_ns": duration, "source_path": relative})
        clips[name] = {**clip, "frames": frames}
    states = selection.get("states", {})
    if set(states) != STATES or any(value not in clips for value in states.values()) or "idle" not in clips:
        raise ValueError("State mapping is incomplete")
    for clip in clips.values():
        if any(clip[key] and clip[key] not in clips for key in ("transition_in", "transition_out")):
            raise ValueError("Selected transition clip is missing")
    actions = selection.get("actions", [])
    if not isinstance(actions, list) or len(actions) > 16:
        raise ValueError("Invalid manual actions")
    for action in actions:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", action.get("id", "")) or not action.get("title") or not action.get("clips") or any(name not in clips for name in action["clips"]):
            raise ValueError("Manual action references an unknown clip")
        if "hold_ms" in action and (action["hold_ms"] != 800 or len(action["clips"]) != 1 or len(clips[action["clips"][0]]["frames"]) != 1):
            raise ValueError("Invalid manual static pose duration")
    icon = selection["icon"]
    payloads["icon.png"], icon_hash = verified_png(source, icon["source"], icon["sha256"], (256, 256))
    declarations = []
    for index, item in enumerate(selection.get("declarations", [])):
        raw = source_file(source, item["source"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != item["sha256"]:
            raise ValueError("Declaration hash mismatch")
        target = f"licenses/source-{index}.txt"
        payloads[target] = raw
        declarations.append({"file": target, "source_path": item["source"], "sha256": digest})
    pack = {"schema_version": 1, "repository": selection["repository"], "upstream_ref": PIN,
            "rights": rights, "canvas": canvas, "ground_y": ground,
            "default_frame": clips[states["idle"]]["frames"][0]["file"],
            "clips": clips, "states": states, "actions": actions,
            "icon": {"file": "icon.png", "sha256": icon_hash, "source_path": icon["source"]}, "declarations": declarations}
    payloads["SOURCES.md"] = ("# Source and permission\n\n" + selection["repository"] + "\n\nCommit: " + PIN + "\n\n" + str(rights["basis"]) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="." + output.name + "-", dir=output.parent))
    backup = stage.with_name(stage.name + "-old")
    try:
        for relative, raw in payloads.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (stage / "asset-pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n")
        if output.exists():
            if not output.is_dir():
                raise ValueError("Output is not an asset directory")
            os.replace(output, backup)
        try:
            os.replace(stage, output)
        except Exception:
            if backup.exists():
                os.replace(backup, output)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return pack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    ref = verify_checkout(args.source)
    selection = json.loads(args.selection.read_text())
    result = import_asset_pack(args.source, selection, args.output, source_ref=ref)
    print(json.dumps({"upstream_ref": result["upstream_ref"], "clips": len(result["clips"]), "frames": sum(len(clip["frames"]) for clip in result["clips"].values())}))


if __name__ == "__main__":
    main()
