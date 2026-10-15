"""Exercise the macOS initializer without network or personal project data."""

import fcntl
import glob
import hashlib
import os
import runpy
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
INITIALIZER = PROJECT / "scripts/initialize-macos.sh"
APP = Path("dist/desktop/课间助手.app/Contents")


class MacInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="campus mac [课间] ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.environment = {**os.environ, "FIXTURE_ROOT": str(self.root)}

    def write(self, relative, text="fixture", executable=False):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if executable:
            path.chmod(0o755)
        return path

    def fixture(self):
        for path in (
            "backend/uv.lock",
            "frontend/package-lock.json",
            "extension/package-lock.json",
            "scripts/build-desktop.py",
            "scripts/package-desktop.py",
            "config/scut-undergraduate-2026-10-14.json",
        ):
            self.write(path)
        self.write(".env.example", "MODEL_API_KEY=\n")
        shutil.copy2(INITIALIZER, self.root / "scripts/initialize-macos.sh")

    def bundle(self):
        self.write(
            APP / "MacOS/CampusCompanion",
            '#!/bin/bash\ncase "${1:-}" in --help|--time-mcp) exit 0;; esac\nprintf "%s\\n" "$@" > "$FIXTURE_ROOT/launched"\n',
            True,
        )
        self.write(APP / "Frameworks/libpython3.12.dylib")
        self.write(APP / "Resources/frontend/dist/index.html")
        self.write(APP / "Resources/extension/.output/chrome-mv3/manifest.json")

    def bash(self, body, *arguments):
        return subprocess.run(
            [
                "/bin/bash",
                "-c",
                'set -euo pipefail\nsource "$1"\nshift\n' + body,
                "test",
                str(INITIALIZER),
                *map(str, arguments),
            ],
            check=False,
            cwd=self.root,
            env=self.environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )

    def run_initializer(self, *arguments):
        return subprocess.run(
            ["/bin/bash", str(self.root / "scripts/initialize-macos.sh"), *arguments],
            check=False,
            cwd=self.root,
            env=self.environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )

    def fake_tools(self):
        self.write("fakebin/node", "#!/bin/bash\necho v22.23.3\n", True)
        self.write("fakebin/npm", "#!/bin/bash\nexit 0\n", True)
        self.write(
            "fakebin/uv",
            """#!/bin/bash
set -eu
if [ "$1" = '--version' ]; then echo 'uv 0.11.19'; exit 0; fi
printf '%s\\n' "$1" >> "$FIXTURE_ROOT/commands"
if [ "$1" = 'sync' ] && [ -f "$FIXTURE_ROOT/fail-sync" ]; then exit 17; fi
if [ "$1" = 'run' ]; then
    if [ -f "$FIXTURE_ROOT/fail-build" ]; then exit 23; fi
    app="$FIXTURE_ROOT/dist/desktop/课间助手.app/Contents"
    mkdir -p "$app/MacOS" "$app/Frameworks" "$app/Resources/frontend/dist" "$app/Resources/extension/.output/chrome-mv3"
    printf '#!/bin/bash\\ncase "${1:-}" in --help|--time-mcp) if [ -f "$FIXTURE_ROOT/fail-runtime" ]; then exit 29; fi; exit 0;; esac\\nprintf "%%s\\\\n" "$@" > "$FIXTURE_ROOT/launched"\\n' > "$app/MacOS/CampusCompanion"
    chmod +x "$app/MacOS/CampusCompanion"
    touch "$app/Frameworks/libpython3.12.dylib" "$app/Resources/frontend/dist/index.html" "$app/Resources/extension/.output/chrome-mv3/manifest.json"
fi
""",
            True,
        )
        self.environment["PATH"] = (
            str(self.root / "fakebin") + ":/usr/bin:/bin:/usr/sbin:/sbin"
        )

    def test_supported_node_versions(self):
        for version, expected in [
            ("v22.12.0", 0),
            ("v22.23.3", 0),
            ("v22.11.0", 1),
            ("v24.1.0", 1),
            ("garbage", 1),
        ]:
            with self.subTest(version=version):
                result = self.bash('campus_node_version_ok "$1"', version)
                self.assertEqual(result.returncode, expected, result.stdout)

    def test_architecture_selection(self):
        for architecture, expected in [("arm64", "arm64"), ("x86_64", "x64")]:
            result = self.bash('campus_architecture "$1"', architecture)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout.strip(), expected)
        self.assertNotEqual(self.bash("campus_architecture i386").returncode, 0)

    def test_checksums_match_and_reject_other_filenames_or_corruption(self):
        archive = self.write("archive.tar.gz", "verified fixture")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        for content, valid in [
            (digest, True),
            (digest + " *archive.tar.gz\n", True),
            (digest + "  other.tar.gz\n", False),
            ("0" * 64, False),
        ]:
            checksums = self.write("checksums", content)
            result = self.bash('campus_verify_checksum "$1" "$2"', archive, checksums)
            self.assertEqual(result.returncode == 0, valid, result.stdout)

    def test_verified_tar_installs_complete_runtime_and_preserves_it_on_bad_checksum(
        self,
    ):
        binary = self.write(
            "payload/node-version/bin/node", "#!/bin/bash\nexit 0\n", True
        )
        self.write("payload/node-version/bin/npm", "companion")
        archive = self.root / "fixture.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(binary.parents[1], arcname="node-version")
        self.write("fixture.sha256", hashlib.sha256(archive.read_bytes()).hexdigest())
        body = """
campus_download() {
    case "$1" in
        *.sha256) cp "$FIXTURE_ROOT/fixture.sha256" "$2" ;;
        *) cp "$FIXTURE_ROOT/fixture.tar.gz" "$2" ;;
    esac
}
installed=$(campus_install_archive https://example.test/node.tar.gz https://example.test/node.sha256 "$1" bin/node)
test -x "$installed"
"""
        destination = self.root / "tools [local]/node"
        result = self.bash(body, destination)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((destination / "bin/npm").is_file())
        self.write("fixture.sha256", "0" * 64)
        result = self.bash(body, destination)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue((destination / "bin/node").is_file())

    def test_fresh_checkout_builds_and_repeated_start_is_offline(self):
        self.fixture()
        self.fake_tools()
        self.write(".env", "MODEL_API_KEY=test-only")
        self.write("model.env", "MODEL_API_KEY=another-fixture")
        self.write("data/campus.db", "private database")
        self.write("backups/fixture.zip", "private backup")
        result = self.run_initializer("--no-launch")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.root / "launched").exists())
        self.assertEqual(
            (self.root / "commands").read_text().splitlines(), ["sync", "run"]
        )
        for path, expected in [
            (".env", "MODEL_API_KEY=test-only"),
            ("model.env", "MODEL_API_KEY=another-fixture"),
            ("data/campus.db", "private database"),
            ("backups/fixture.zip", "private backup"),
        ]:
            self.assertEqual((self.root / path).read_text(), expected)
        self.environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        result = self.run_initializer()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.root / "launched").read_text().splitlines(),
            ["--data-dir", str(self.root), "--project"],
        )
        self.assertEqual(
            (self.root / "commands").read_text().splitlines(), ["sync", "run"]
        )

    def test_existing_bundle_initializes_only_missing_configuration(self):
        self.fixture()
        self.bundle()
        self.environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        result = self.run_initializer("--no-launch")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.root / ".env").read_bytes(), (self.root / ".env.example").read_bytes()
        )
        self.assertFalse((self.root / ".tools").exists())

    def test_failed_dependencies_stop_build_and_release_lock_for_retry(self):
        self.fixture()
        self.fake_tools()
        self.write("fail-sync")
        result = self.run_initializer("--no-launch")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.root / "commands").read_text().splitlines(), ["sync"])
        self.assertTrue((self.root / ".tools/macos-build-incomplete").exists())
        self.assertIn("17", (self.root / ".tools/macos-initialize.log").read_text())
        (self.root / "fail-sync").unlink()
        result = self.run_initializer("--no-launch")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.root / ".tools/macos-build-incomplete").exists())

    def test_failed_rebuild_cannot_be_mistaken_for_complete_bundle(self):
        self.fixture()
        self.bundle()
        self.fake_tools()
        self.write("fail-build")
        result = self.run_initializer("--rebuild", "--no-launch")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotEqual(
            self.bash('campus_bundle_ready "$1"', self.root).returncode, 0
        )
        (self.root / "fail-build").unlink()
        result = self.run_initializer("--no-launch")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.root / "commands").read_text().splitlines(),
            ["sync", "run", "sync", "run"],
        )

    def test_packaged_runtime_failure_is_not_reported_as_success(self):
        self.fixture()
        self.fake_tools()
        self.write("fail-runtime")
        result = self.run_initializer("--no-launch")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("29", result.stdout)
        self.assertTrue((self.root / ".tools/macos-build-incomplete").exists())
        self.assertFalse((self.root / ".env").exists())

    def test_packaging_globs_treat_project_brackets_literally_and_keep_file_patterns(
        self,
    ):
        namespace = runpy.run_path(str(PROJECT / "scripts/package-desktop.py"))
        first = self.write("hooks/hook-first.py")
        second = self.write("hooks/hook-second.py")
        pattern = str(self.root / "hooks/hook-*.py")
        original = glob.glob
        self.assertEqual(glob.glob(pattern), [])
        with namespace["literal_project_globs"](self.root):
            self.assertEqual(set(glob.glob(pattern)), {str(first), str(second)})
            self.assertEqual(
                set(glob.glob(str(self.root / "hook*/hook-*.py"))),
                {str(first), str(second)},
            )
            self.assertEqual(
                set(glob.glob(os.fsencode(pattern))),
                {os.fsencode(first), os.fsencode(second)},
            )
        self.assertIs(glob.glob, original)

    def test_packaging_glob_wrapper_restores_global_state_after_failure(self):
        namespace = runpy.run_path(str(PROJECT / "scripts/package-desktop.py"))
        original = glob.glob
        with (
            self.assertRaisesRegex(RuntimeError, "fixture failure"),
            namespace["literal_project_globs"](self.root),
        ):
            raise RuntimeError("fixture failure")
        self.assertIs(glob.glob, original)

    def test_concurrent_initialization_does_not_modify_configuration(self):
        self.fixture()
        lock = self.root / ".tools/macos-initialize.lock"
        lock.parent.mkdir()
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_initializer("--no-launch")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("already running", result.stdout)
            self.assertFalse((self.root / ".env").exists())

    def test_download_failures_retry_three_times_and_remove_partial_file(self):
        result = self.bash("""
curl() {
    printf 'attempt\\n' >> "$FIXTURE_ROOT/attempts"
    while [ "$#" -gt 0 ]; do
        if [ "$1" = '--output' ]; then printf partial > "$2"; break; fi
        shift
    done
    return 1
}
sleep() { :; }
campus_download https://example.test/archive.tar.gz "$FIXTURE_ROOT/download.tar.gz"
""")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(len((self.root / "attempts").read_text().splitlines()), 3)
        self.assertFalse((self.root / "download.tar.gz").exists())
        self.assertFalse((self.root / "download.tar.gz.partial").exists())

    def test_successful_download_cleanup_works_inside_command_substitution(self):
        result = self.bash("""
curl() {
    while [ "$#" -gt 0 ]; do
        if [ "$1" = '--output' ]; then printf complete > "$2"; return 0; fi
        shift
    done
    return 1
}
downloaded=$(campus_download https://example.test/archive.tar.gz "$FIXTURE_ROOT/download.tar.gz")
test "$(cat "$FIXTURE_ROOT/download.tar.gz")" = complete
""")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.root / "download.tar.gz.partial").exists())

    def test_incomplete_repository_fails_before_downloading(self):
        self.root.joinpath("scripts").mkdir()
        shutil.copy2(INITIALIZER, self.root / "scripts/initialize-macos.sh")
        result = self.run_initializer("--no-launch")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("complete repository", result.stdout)
        self.assertFalse((self.root / ".tools").exists())


if __name__ == "__main__":
    unittest.main()
