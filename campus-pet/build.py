"""Build a native Mac pet and reuse the existing assistant without copying secrets."""
import argparse
import os
import platform
import plistlib
import shutil
import struct
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--reuse-service", action="store_true", help="Reuse this project's previously built service")
args = parser.parse_args()
project = root.parent
python = project / "backend/.venv/bin/python"
build = root / "build"
build.mkdir(exist_ok=True)
environment = os.environ.copy()
node = project / ".tools/macos/node/bin"
if node.is_dir():
    environment["PATH"] = str(node) + os.pathsep + environment.get("PATH", "")
environment["PYINSTALLER_CONFIG_DIR"] = str(build / "pyinstaller-cache")
service = build / "backend-dist/CampusCompanion"
if not args.reuse_service:
    print("Building current assistant frontend and frozen service…", flush=True)
    subprocess.run(["npm", "--prefix", str(project / "frontend"), "run", "build"], env=environment, check=True)
    if not (project / "extension/.output/chrome-mv3/manifest.json").is_file():
        raise SystemExit("Build the original production timetable extension first (see its desktop documentation).")
    with (build / "service-build.log").open("w") as log:
        subprocess.run([
            str(python), str(project / "scripts/package-desktop.py"), "--noconfirm", "--clean",
            "--distpath", str(build / "backend-dist"), "--workpath", str(build / "backend-work"),
            str(project / "scripts/desktop.spec"),
        ], cwd=project, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
if not (service / "CampusCompanion").is_file():
    raise SystemExit("Missing service. Run build.py without --reuse-service first.")
app = root / "dist/课间桌宠.app"
contents = app / "Contents"
macos = contents / "MacOS"
resources = contents / "Resources"
macos.mkdir(parents=True, exist_ok=True)
resources.mkdir(parents=True, exist_ok=True)
print("Compiling native pet…", flush=True)
cache = build / "swift-cache"
cache.mkdir(exist_ok=True)
subprocess.run([
    "xcrun", "swiftc", "-swift-version", "5", "-O", "-module-cache-path", str(cache),
    "-target", platform.machine() + "-apple-macosx13.0",
    "-framework", "AppKit", "-framework", "WebKit",
    *[str(path) for path in sorted((root / "Sources").glob("*.swift"))],
    "-o", str(macos / "CampusPet"),
], check=True)
destination = resources / "service"
if destination.exists():
    shutil.rmtree(destination)
shutil.copytree(service, destination, symlinks=True)
shutil.copy2(root / "Resources/Bridge.js", resources / "Bridge.js")
shutil.copy2(root / "Resources/naiwa.png", resources / "naiwa.png")
animation_destination = resources / "Animations"
if animation_destination.exists():
    shutil.rmtree(animation_destination)
shutil.copytree(root / "Resources/Animations", animation_destination)
iconset = build / "AppIcon.iconset"
iconset.mkdir(exist_ok=True)
for size in (16, 32, 128, 256, 512):
    for retina in (False, True):
        pixels = size * (2 if retina else 1)
        name = f"icon_{size}x{size}" + ("@2x" if retina else "") + ".png"
        subprocess.run(["sips", "-z", str(pixels), str(pixels), str(resources / "naiwa.png"), "--out", str(iconset / name)], stdout=subprocess.DEVNULL, check=True)
# ICNS is a container of already encoded PNG representations. Package the
# system-resized PNGs directly; this also works without iconutil's GUI services.
entries = [(b"icp4", 16, False), (b"icp5", 32, False), (b"icp6", 32, True),
           (b"ic07", 128, False), (b"ic08", 256, False), (b"ic09", 512, False),
           (b"ic10", 512, True), (b"ic11", 16, True), (b"ic12", 32, True),
           (b"ic13", 128, True), (b"ic14", 256, True)]
chunks = []
for tag, size, retina in entries:
    name = f"icon_{size}x{size}" + ("@2x" if retina else "") + ".png"
    png = (iconset / name).read_bytes()
    chunks.append(struct.pack(">4sI", tag, len(png) + 8) + png)
body = b"".join(chunks)
(resources / "AppIcon.icns").write_bytes(struct.pack(">4sI", b"icns", len(body) + 8) + body)
# Location only, never the original .env, API keys, databases or screenshots.
(resources / "source-project.txt").write_text(str(project), encoding="utf8")
with (contents / "Info.plist").open("wb") as handle:
    plistlib.dump({
        "CFBundleExecutable": "CampusPet", "CFBundleIdentifier": "cn.campuscompanion.pet",
        "CFBundleName": "课间桌宠", "CFBundleDisplayName": "课间桌宠",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1", "LSMinimumSystemVersion": "13.0", "LSUIElement": True,
        "CFBundleIconFile": "AppIcon",
        "NSHighResolutionCapable": True,
        "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
    }, handle)
subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
print("Built:", app, flush=True)
