"""Build, verify and package a version; clean only known generated artifacts.

Run with backend/.venv/bin/python. No paid model calls or personal-data writes.
An existing release is never overwritten; an interrupted build keeps its hidden
staging folder for inspection and leaves previous versions untouched.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parent
EXCLUDED_PARTS = {
    ".git", ".tools", ".venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", "build", "dist", ".output", ".output-e2e", ".wxt", "data",
    "backups", "test-results", "playwright-report", "desktop-extension",
}
PREVIEWS = ("Demo2.2后续开发预览", "Demo2.2后续开发预览-课表识别")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allowed_source(relative):
    path = Path(relative)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not (set(path.parts) & EXCLUDED_PARTS)
        and path.name != ".DS_Store"
        and not (path.name.startswith(".env") and path.name != ".env.example")
        and path.name != "model.env"
        and path.suffix.lower() not in {".db", ".sqlite", ".sqlite3", ".log", ".pyc"}
        and path.as_posix() != "campus-pet/art/video/source.mp4"
    )


def private_values(project):
    # Parse locally; never include credentials in arguments, output or archives.
    from dotenv import dotenv_values

    values = set()
    for name in (".env", "model.env"):
        path = project / name
        if path.is_file():
            for key, value in dotenv_values(path).items():
                if value and len(value) >= 8 and re.search(
                    r"KEY|TOKEN|SECRET|PASSWORD", key, re.IGNORECASE
                ):
                    values.add(value.encode())
    return values


def check_stream(stream, secrets):
    overlap = max(map(len, secrets), default=1) - 1
    tail = b""
    for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
        data = tail + chunk
        if any(secret in data for secret in secrets):
            raise RuntimeError("Private credential detected; release stopped.")
        tail = data[-overlap:] if overlap else b""


def source_archive(project, destination, secrets):
    files = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=project,
    ).decode().split("\0")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(set(filter(None, files))):
            path = project / relative
            if not allowed_source(relative) or not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("Unexpected source link/directory; inspect source.")
            with path.open("rb") as stream:
                check_stream(stream, secrets)
            archive.write(path, "source/" + relative)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Source ZIP integrity check failed.")


def verify_bundle(app, version, secrets):
    import plistlib

    with (app / "Contents/Info.plist").open("rb") as stream:
        if plistlib.load(stream)["CFBundleShortVersionString"] != version:
            raise RuntimeError("Bundle version mismatch.")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    for path in app.rglob("*"):
        if path.name in {".env", "model.env", "campus.db", "agent.db"}:
            raise RuntimeError("Private file detected in application.")
        if path.is_file():
            with path.open("rb") as stream:
                check_stream(stream, secrets)


def cleanup_generated(project, workspace):
    """Fixed allowlist only; never recurse into dependencies or personal data."""
    targets = [
        project / "campus-pet/build", project / "campus-pet/dist",
        project / "frontend/test-results", project / "frontend/playwright-report",
        project / "backend/.pytest_cache", project / "backend/.ruff_cache",
        project / ".ruff_cache", project / "scripts/tests/__pycache__",
    ]
    for name in PREVIEWS:
        preview = workspace / name
        if preview.is_symlink():
            raise RuntimeError("Linked preview directory; cleanup refused.")
        if preview.exists():
            manifest = json.loads((preview / "manifest.json").read_text())
            if "development-preview" not in (manifest.get("type"), manifest.get("stage")):
                raise RuntimeError("Unrecognized preview; cleanup refused.")
            targets.append(preview)
    # Preflight all targets before removing anything. Do not follow symlinks.
    for target in targets:
        if target.is_symlink() or target.resolve() != target.absolute():
            raise RuntimeError("Linked cleanup target; cleanup refused.")
    removed = []
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(str(target.relative_to(workspace)))
    return removed


def run_checks(project, stage, version):
    python = str(project / "backend/.venv/bin/python")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project / "backend")
    env["PATH"] = str(project / ".tools/macos/node/bin") + os.pathsep + env.get("PATH", "")
    commands = [
        ("extension_tests", ["npm", "--prefix", "extension", "test"]),
        ("extension_types", ["npm", "--prefix", "extension", "run", "typecheck"]),
        ("extension_build", ["npm", "--prefix", "extension", "run", "build"]),
        # Build the current frontend and binary before tests consume static assets.
        ("build", [python, "campus-pet/build.py", "--output-dir", str(stage),
                   "--version", version]),
        ("backend", [python, "-m", "pytest", "backend/tests", "scripts/tests", "-q"]),
        ("frontend", ["npm", "--prefix", "frontend", "test"]),
        ("browser", [str(project / "frontend/node_modules/.bin/playwright"), "test",
                     "--config=frontend/playwright.pet.config.ts"]),
        ("native_logic", [python, "campus-pet/tests/run_native_tests.py"]),
        ("native_health_transport", [python, "campus-pet/tests/run_health_transport_tests.py"]),
        ("native_integration", [python, "campus-pet/verify.py", "--app", str(stage / "课间桌宠.app")]),
        ("frozen_pdf", [python, "scripts/verify-frozen-timetable.py", "--service",
                        str(stage / "课间桌宠.app/Contents/Resources/service/CampusCompanion"),
                        "--output", str(stage / "打包PDF检查.json")]),
        ("frozen_ab", [python, "scripts/verify-frozen-ab.py", "--service",
                       str(stage / "课间桌宠.app/Contents/Resources/service/CampusCompanion"),
                       "--output", str(stage / "甲乙冻结联调检查.json")]),
        ("frozen_b_interaction", [python, "scripts/verify-frozen-b-interaction.py", "--service",
                                  str(stage / "课间桌宠.app/Contents/Resources/service/CampusCompanion"),
                                  "--output", str(stage / "乙交互冻结检查.json")]),
    ]
    results = {}
    for name, command in commands:
        print("Release check:", name, flush=True)
        log_path = stage / (name + ".log")
        command_env = env
        if name.startswith("extension_"):
            # Production builds must never inherit an E2E adapter/origin or
            # silently produce a bridge without the observed school scope.
            command_env = {
                **env,
                "PUBLIC_ORIGIN": "http://127.0.0.1:5173",
                "SCUT_ADAPTER_PATH": str(project / "config/scut-undergraduate-2026-10-14.json"),
            }
        try:
            with log_path.open("w") as log:
                subprocess.run(command, cwd=project, env=command_env, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
        except subprocess.CalledProcessError as failure:
            if name != "native_integration":
                raise
            verification = project / "campus-pet/build/verification"
            try:
                result = json.loads((verification / "result.json").read_text())
            except (OSError, ValueError):
                raise failure
            if result.get("passed") is not False or result.get("error") != "The request timed out.":
                raise
            # A recorded network timeout permits one fresh isolated run. No
            # business error is retried; a second failure still aborts release.
            shutil.copytree(verification, stage / "native-attempt-1")
            log_path.rename(stage / "native_integration-attempt-1.log")
            print("Native request timeout recorded; retrying once with isolated data", flush=True)
            with log_path.open("w") as log:
                subprocess.run(command, cwd=project, env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            results[name] = "passed after one recorded timeout retry"
        else:
            results[name] = "passed"
    shutil.copy2(project / "campus-pet/build/verification/result.json", stage / "原生集成检查.json")
    health_metrics = project / "campus-pet/build/verification/health-diagnostics.json"
    if health_metrics.is_file():
        shutil.copy2(health_metrics, stage / "原生健康诊断.json")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="e.g. 2.3.0")
    parser.add_argument("--keep-generated", action="store_true", help="Retain caches and previews")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("Use a three-part numeric version, e.g. 2.4.7")
    label = "Demo" + re.sub(r"\.0$", "", args.version)
    final = WORKSPACE / label
    stage = WORKSPACE / (".Demo" + args.version + "-staging")
    if final.exists() or stage.exists():
        parser.error("Release or staging directory already exists; no files overwritten.")
    release_notes = PROJECT / "docs/releases" / (label + ".md")
    if not release_notes.is_file():
        parser.error("Write docs/releases/" + label + ".md before releasing.")
    if (PROJECT / "campus-pet/VERSION").read_text().strip() != args.version:
        parser.error("Update campus-pet/VERSION before releasing.")
    secrets = private_values(PROJECT)
    stage.mkdir()
    checks = run_checks(PROJECT, stage, args.version)
    app = stage / "课间桌宠.app"
    verify_bundle(app, args.version, secrets)
    shutil.copy2(release_notes, stage / "使用说明.md")
    evidence = PROJECT / "docs/roadmap/evidence"
    for source, destination in (
        ("timetable-recognition-review.png", "课表校对界面.png"),
        ("deepseek-smoke-test.json", "DeepSeek联调-开发阶段.json"),
        ("timetable-text-review.png", "文字课表校对界面.png"),
        ("today-plan-review.png", "当日日程预览.png"),
        ("course-change-review.png", "课程调整预览.png"),
        ("timetable-text-real-model.json", "文字课表联调-开发阶段.json"),
    ):
        if (evidence / source).exists():
            shutil.copy2(evidence / source, stage / destination)
    source_archive(PROJECT, stage / (label + "-源码.zip"), secrets)
    app_zip = stage / (label + "-Mac-AppleSilicon.zip")
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(app_zip)], check=True)
    with zipfile.ZipFile(app_zip) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Application ZIP integrity check failed.")
    validation = {
        "passed": True, "version": args.version, "checks": checks,
        "application_signature": "verified", "application_zip_crc": "passed",
        "source_zip_crc": "passed", "private_values_scan": "passed",
        "scope": "current working tree; isolated automated data; no paid model calls",
        "real_samples_acceptance": "pending; see release notes",
    }
    (stage / "验证结果.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n")
    manifest = {
        "release": label, "version": args.version,
        "created_at": datetime.now(UTC).isoformat(),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "source": "current working tree, including uncommitted changes",
        "platform": "macOS Apple Silicon", "minimum_macos": "13.0",
        "checks": checks, "credentials_and_personal_data_in_package": False,
        "release_basis": "current version built and verified independently; no historical baseline required",
        "real_model_smoke": "development evidence copied; no paid calls during release",
        "real_scut_accuracy_acceptance": "pending; no 30-sample benchmark",
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    # Scan documentation and logs too before making the release visible.
    for path in stage.iterdir():
        if path.is_file() and path.suffix != ".zip":
            with path.open("rb") as stream:
                check_stream(stream, secrets)
    stage.rename(final)
    removed = [] if args.keep_generated else cleanup_generated(PROJECT, WORKSPACE)
    (final / "整理记录.json").write_text(json.dumps({
        "removed_generated_paths": removed, "preserved": [
            "existing archives", label, "active source project", ".env / model.env", "data / backups",
            "installed dependencies", "development taskbook",
        ],
    }, ensure_ascii=False, indent=2) + "\n")
    (final / "SHA256SUMS.txt").write_text("".join(
        sha256(path) + "  " + path.name + "\n"
        for path in sorted(final.iterdir()) if path.is_file() and path.name != "SHA256SUMS.txt"
    ))
    (WORKSPACE / "README.md").write_text(
        "# 课间奶蛙\n\n"
        + "当前版本 **" + label + "**（" + args.version + "），已从当前源码独立构建并验证。\n\n"
        + "- [打开最新桌宠](" + label + "/课间桌宠.app)\n"
        + "- [下载最新应用包](" + label + "/" + label + "-Mac-AppleSilicon.zip)\n"
        + "- [当前源码快照](" + label + "/" + label + "-源码.zip)\n"
        + "- [使用说明与已知限制](" + label + "/使用说明.md)\n"
        + "- [开发任务书](" + PROJECT.name + "/docs/roadmap/demo2.2-development-taskbook.md)\n\n"
        + "活跃源码与个人资料在 `" + PROJECT.name + "/`；目录名保留以兼容既有路径。"
        + "Key 在私有配置中，资料在 data/、backups/ 中，不进入发布包。\n\n"
        + "每版开发后按 [发布流程](" + PROJECT.name + "/docs/releases/发布流程.md)"
        + "重新验证、打包并清理旧预览及构建缓存。历史验证材料见“资料归档”。\n"
    )
    print("Release complete:", final, flush=True)


if __name__ == "__main__":
    main()
