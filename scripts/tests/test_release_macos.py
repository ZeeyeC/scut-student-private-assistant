"""Protect current release completeness, private files and existing archives."""

import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "release_macos", Path(__file__).resolve().parents[1] / "release-macos.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseSafetyTests(unittest.TestCase):
    def test_release_requires_accepted_visual_comparison_after_actual_native_capture(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            project=Path(temp);stage=project/"stage";stage.mkdir()
            verification=project/"campus-pet/build/verification";verification.mkdir(parents=True)
            (verification/"result.json").write_text('{"passed":true}')
            calls=[]
            def external(command,**kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command,0)
            with patch.object(release.subprocess,"run",side_effect=external):
                release.run_checks(project,stage,"2.5.1")
            visual=[c for c in calls if "scripts/verify-ui-reference.py" in c]
            self.assertEqual(len(visual),1,"Visual fidelity is a required release gate")
            self.assertIn("--native",visual[0]);self.assertNotIn("--update-reference",visual[0])
            native=next(c for c in calls if "campus-pet/verify.py" in c)
            self.assertGreater(calls.index(visual[0]),calls.index(native))

    def test_cleanup_preserves_data_when_checkout_is_outside_archive_workspace(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            base=Path(temp);project=base/"checkouts/agentbuild";workspace=base/"archives";workspace.mkdir()
            generated=project/"campus-pet/build";generated.mkdir(parents=True)
            personal=project/"data/preserve.txt";personal.parent.mkdir();personal.write_text("preserve")
            removed=release.cleanup_generated(project,workspace)
            self.assertIn("../checkouts/agentbuild/campus-pet/build",removed)
            self.assertFalse(generated.exists());self.assertEqual(personal.read_text(),"preserve")

    def test_extension_release_uses_observed_school_adapter_and_local_origin(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            project = Path(temp)
            stage = project / "stage"
            stage.mkdir()
            verification = project / "campus-pet/build/verification"
            verification.mkdir(parents=True)
            (verification / "result.json").write_text('{"passed":true}')
            extension_environments = []

            def external(command, **kwargs):
                if command[:3] == ["npm", "--prefix", "extension"]:
                    extension_environments.append(kwargs["env"])
                return subprocess.CompletedProcess(command, 0)

            with patch.object(release.subprocess, "run", side_effect=external):
                release.run_checks(project, stage, "2.4.9")
            self.assertEqual(len(extension_environments), 3)
            for env in extension_environments:
                self.assertEqual(env.get("PUBLIC_ORIGIN"), "http://127.0.0.1:5173")
                self.assertEqual(
                    env.get("SCUT_ADAPTER_PATH"),
                    str(project / "config/scut-undergraduate-2026-10-14.json"),
                )

    def test_native_timeout_keeps_first_failure_and_requires_a_successful_retry(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            project = Path(temp)
            stage = project / "stage"
            stage.mkdir()
            verification = project / "campus-pet/build/verification"
            verification.mkdir(parents=True)
            native_calls = []

            def external(command, **kwargs):
                if "campus-pet/verify.py" in command:
                    native_calls.append(command)
                    if len(native_calls) == 1:
                        (verification / "result.json").write_text(
                            json.dumps(
                                {"passed": False, "error": "The request timed out."}
                            )
                        )
                        kwargs["stdout"].write("recorded health timeout\n")
                        raise subprocess.CalledProcessError(1, command)
                    (verification / "result.json").write_text(
                        '{"passed":true,"error":""}'
                    )
                return subprocess.CompletedProcess(command, 0)

            with patch.object(release.subprocess, "run", side_effect=external):
                results = release.run_checks(project, stage, "2.4.7")
            self.assertEqual(len(native_calls), 2)
            self.assertFalse(
                json.loads((stage / "native-attempt-1/result.json").read_text())[
                    "passed"
                ]
            )
            self.assertIn(
                "recorded health timeout",
                (stage / "native_integration-attempt-1.log").read_text(),
            )
            self.assertTrue(
                json.loads((stage / "原生集成检查.json").read_text())["passed"]
            )
            self.assertIn("native_integration", results)

    def test_native_business_failure_is_not_retried_or_accepted(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            project = Path(temp)
            stage = project / "stage"
            stage.mkdir()
            verification = project / "campus-pet/build/verification"
            verification.mkdir(parents=True)
            native_calls = []

            def external(command, **kwargs):
                if "campus-pet/verify.py" in command:
                    native_calls.append(command)
                    (verification / "result.json").write_text(
                        '{"passed":false,"error":"wrong task completed"}'
                    )
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            with (
                patch.object(release.subprocess, "run", side_effect=external),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                release.run_checks(project, stage, "2.4.7")
            self.assertEqual(len(native_calls), 1)
            self.assertFalse((stage / "原生集成检查.json").exists())

    def test_two_native_timeouts_still_abort_release(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            project = Path(temp)
            stage = project / "stage"
            stage.mkdir()
            verification = project / "campus-pet/build/verification"
            verification.mkdir(parents=True)
            native_calls = []

            def external(command, **kwargs):
                if "campus-pet/verify.py" in command:
                    native_calls.append(command)
                    (verification / "result.json").write_text(
                        '{"passed":false,"error":"The request timed out."}'
                    )
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            with (
                patch.object(release.subprocess, "run", side_effect=external),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                release.run_checks(project, stage, "2.4.7")
            self.assertEqual(len(native_calls), 2)
            self.assertFalse((stage / "原生集成检查.json").exists())

    def test_private_and_generated_sources_excluded_even_if_tracked(self):
        for name in (
            ".env",
            ".env.local",
            "model.env",
            "data/uploads/photo.png",
            "backups/snapshot.zip",
            "backend/.venv/lib/site.py",
            "campus-pet/build/raw.mov",
            "frontend/node_modules/key.json",
            ".git/config",
            "campus.db",
            ".DS_Store",
            "../outside.py",
            "campus-pet/art/video/source.mp4",
        ):
            with self.subTest(name=name):
                self.assertFalse(release.allowed_source(name))
        self.assertTrue(release.allowed_source(".env.example"))
        self.assertTrue(release.allowed_source("backend/app/main.py"))

    def test_credentials_detected_across_read_boundaries(self):
        secret = b"private-test-credential"
        body = b"x" * (4 * 1024 * 1024 - 3) + secret
        with self.assertRaisesRegex(RuntimeError, "credential"):
            release.check_stream(io.BytesIO(body), {secret})

    def test_source_archive_contains_current_new_files_without_private_files(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root = Path(temp)
            (root / "new.py").write_text("new code")
            (root / ".env").write_text("MODEL_API_KEY=private-test-credential")
            target = root / "source.zip"
            with patch.object(
                release.subprocess, "check_output", return_value=b"new.py\0.env\0"
            ):
                release.source_archive(root, target, {b"private-test-credential"})
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.namelist(), ["source/new.py"])

    def test_cleanup_keeps_baseline_current_release_dependencies_and_data(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            workspace = Path(temp).resolve()
            project = workspace / "source"
            keep = [
                "Demo2.2/app",
                "Demo2.3/app",
                "source/data/file",
                "source/.env",
                "source/backend/.venv/bin/python",
                "source/.tools/runtime",
                "source/backups/save",
            ]
            for name in keep:
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("preserve")
            generated = project / "campus-pet/build"
            generated.mkdir(parents=True)
            (generated / "cache").write_text("generated")
            preview = workspace / release.PREVIEWS[0]
            preview.mkdir()
            (preview / "manifest.json").write_text(
                json.dumps({"stage": "development-preview"})
            )
            before = {name: (workspace / name).read_bytes() for name in keep}
            release.cleanup_generated(project, workspace)
            self.assertFalse(generated.exists())
            self.assertFalse(preview.exists())
            self.assertEqual(
                {name: (workspace / name).read_bytes() for name in keep}, before
            )
            self.assertTrue(all((workspace / name).is_file() for name in keep))

    def test_current_release_is_complete_without_any_historical_baseline(self):
        # Requiring an old archive or omitting an output must fail this test.
        for version, label in (("2.4.7", "Demo2.4.7"), ("1.0.0", "Demo1.0")):
            with (
                self.subTest(version=version),
                tempfile.TemporaryDirectory(dir="/private/tmp") as temp,
            ):
                workspace = Path(temp).resolve()
                project = workspace / "source"
                (project / "campus-pet").mkdir(parents=True)
                (project / "docs/releases").mkdir(parents=True)
                (project / "campus-pet/VERSION").write_text(version)
                (project / f"docs/releases/{label}.md").write_text(
                    "Current scope and pending real samples"
                )
                (project / "README.md").write_text("Current release")
                subprocess.run(["git", "init", "-q", str(project)], check=True)
                subprocess.run(["git", "add", "."], cwd=project, check=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=Release test",
                        "-c",
                        "user.email=release@example.invalid",
                        "commit",
                        "-qm",
                        "fixture",
                    ],
                    cwd=project,
                    check=True,
                )
                (project / "current.py").write_text("current uncommitted source")

                def expensive_checks(project, stage, version):
                    app = stage / "课间桌宠.app"
                    app.mkdir()
                    (app / "binary").write_bytes(b"synthetic signed-app fixture")
                    return {"backend": "passed", "build": "passed"}

                real_run = subprocess.run

                def platform_command(command, real_run=real_run, **kwargs):
                    if command[0] == "ditto":
                        with zipfile.ZipFile(command[-1], "w") as archive:
                            archive.write(
                                Path(command[-2]) / "binary", "课间桌宠.app/binary"
                            )
                        return subprocess.CompletedProcess(command, 0)
                    return real_run(command, **kwargs)

                with (
                    patch.object(release, "PROJECT", project),
                    patch.object(release, "WORKSPACE", workspace),
                    patch.object(release, "run_checks", side_effect=expensive_checks),
                    patch.object(release, "verify_bundle"),
                    patch.object(
                        release.subprocess, "run", side_effect=platform_command
                    ),
                    patch("sys.argv", ["release-macos.py", "--version", version]),
                ):
                    release.main()
                final = workspace / label
                for name in (
                    "课间桌宠.app",
                    label + "-Mac-AppleSilicon.zip",
                    label + "-源码.zip",
                    "使用说明.md",
                    "验证结果.json",
                    "manifest.json",
                    "SHA256SUMS.txt",
                ):
                    self.assertTrue((final / name).exists(), name)
                with zipfile.ZipFile(final / (label + "-源码.zip")) as archive:
                    self.assertEqual(
                        archive.read("source/current.py"), b"current uncommitted source"
                    )
                self.assertFalse((workspace / ".Demo2.4.7-staging").exists())

    def test_release_honors_the_configured_available_browser(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            project = Path(temp)
            stage = project / "stage"
            stage.mkdir()
            verification = project / "campus-pet/build/verification"
            verification.mkdir(parents=True)
            (verification / "result.json").write_text('{"passed":true}')
            with patch.dict(release.os.environ, {"PET_BROWSER_CHANNEL": "chrome"}):

                def external_command(command, **kwargs):
                    if kwargs["env"]["PET_BROWSER_CHANNEL"] != "chrome":
                        raise RuntimeError("Release forced an unavailable browser")
                    return subprocess.CompletedProcess(command, 0)

                with patch.object(
                    release.subprocess, "run", side_effect=external_command
                ):
                    release.run_checks(project, stage, "2.4.7")

    def test_unrecognized_preview_prevents_all_cleanup(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            workspace = Path(temp).resolve()
            project = workspace / "source"
            generated = project / "campus-pet/build"
            generated.mkdir(parents=True)
            preview = workspace / release.PREVIEWS[0]
            preview.mkdir()
            (preview / "manifest.json").write_text("{}")
            with self.assertRaisesRegex(RuntimeError, "Unrecognized"):
                release.cleanup_generated(project, workspace)
            self.assertTrue(generated.is_dir())

    def test_symlinked_cache_cannot_delete_personal_directory(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            workspace = Path(temp).resolve()
            project = workspace / "source"
            personal = project / "data"
            personal.mkdir(parents=True)
            (project / "campus-pet").mkdir()
            (project / "campus-pet/build").symlink_to(
                personal, target_is_directory=True
            )
            with self.assertRaisesRegex(RuntimeError, "Linked"):
                release.cleanup_generated(project, workspace)
            self.assertTrue(personal.is_dir())
