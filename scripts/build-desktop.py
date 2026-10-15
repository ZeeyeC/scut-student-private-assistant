"""Build on the target OS with Python 3.12 + Node 22; users need neither."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument(
    "--skip-web",
    action="store_true",
    help="Reuse explicitly prebuilt frontend/production extension",
)
args = parser.parse_args()
if sys.version_info[:2] != (3, 12):
    parser.error("Build with Python 3.12")
npm = "npm.cmd" if sys.platform == "win32" else "npm"
if not args.skip_web:
    subprocess.run([npm, "--prefix", "frontend", "ci"], cwd=root, check=True)
    subprocess.run([npm, "--prefix", "frontend", "run", "build"], cwd=root, check=True)
    subprocess.run([npm, "--prefix", "extension", "ci"], cwd=root, check=True)
    env = {
        **os.environ,
        "PUBLIC_ORIGIN": "http://127.0.0.1:5173",
        "SCUT_ADAPTER_PATH": str(
            root / "config" / "scut-undergraduate-2026-10-14.json"
        ),
        "WXT_OUT_DIR": ".output",
    }
    subprocess.run(
        [npm, "--prefix", "extension", "run", "build"], cwd=root, env=env, check=True
    )
for resource in (
    root / "frontend/dist/index.html",
    root / "extension/.output/chrome-mv3/manifest.json",
):
    if not resource.is_file():
        raise SystemExit(f"Missing built resource: {resource}")
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(root / "dist/desktop"),
        "--workpath",
        str(root / "build/desktop"),
        str(root / "scripts/desktop.spec"),
    ],
    cwd=root,
    env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(root / "build/pyinstaller-cache")},
    check=True,
)
# Preserve macOS bundle symlinks/permissions when downloading CI artifacts.
if sys.platform == "darwin":
    subprocess.run(
        [
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(root / "dist/desktop/课间助手.app"),
            str(root / "dist/desktop/课间助手-macOS.zip"),
        ],
        check=True,
    )
elif sys.platform == "win32":
    shutil.make_archive(
        str(root / "dist/desktop/CampusCompanion-Windows"),
        "zip",
        root_dir=root / "dist/desktop",
        base_dir="CampusCompanion",
    )
print("Built:", root / "dist/desktop")
