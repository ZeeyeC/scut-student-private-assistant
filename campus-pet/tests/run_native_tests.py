"""Compile and run native behavior checks without opening the user's app."""

import platform
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="campus-pet-native-tests-") as temporary:
    output = Path(temporary)
    sources = sorted(
        path for path in (root / "Sources").glob("*.swift") if path.name != "main.swift"
    )
    subprocess.run(
        [
            "xcrun",
            "swiftc",
            "-swift-version",
            "5",
            "-module-cache-path",
            str(output / "cache"),
            "-target",
            platform.machine() + "-apple-macosx13.0",
            "-framework",
            "AppKit",
            "-framework",
            "WebKit",
            *map(str, sources),
            str(root / "tests/NativeTests.swift"),
            str(root / "tests/BrowserLaunchPolicyTests.swift"),
            str(root / "tests/WorkspaceWindowTests.swift"),
            str(root / "tests/PetAssetTests.swift"),
            "-o",
            str(output / "checks"),
        ],
        check=True,
    )
    subprocess.run([str(output / "checks")], check=True)
