"""Protect private files and baseline releases during release housekeeping."""

import importlib.util
import io
import json
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
    def test_private_and_generated_sources_excluded_even_if_tracked(self):
        for name in (
            ".env", ".env.local", "model.env", "data/uploads/photo.png",
            "backups/snapshot.zip", "backend/.venv/lib/site.py", "campus-pet/build/raw.mov",
            "frontend/node_modules/key.json", ".git/config", "campus.db", ".DS_Store",
            "../outside.py", "campus-pet/art/video/source.mp4",
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
            with patch.object(release.subprocess, "check_output", return_value=b"new.py\0.env\0"):
                release.source_archive(root, target, {b"private-test-credential"})
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.namelist(), ["source/new.py"])

    def test_cleanup_keeps_baseline_current_release_dependencies_and_data(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            workspace = Path(temp).resolve()
            project = workspace / "source"
            keep = ["Demo2.2/app", "Demo2.3/app", "source/data/file", "source/.env",
                    "source/backend/.venv/bin/python", "source/.tools/runtime", "source/backups/save"]
            for name in keep:
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("preserve")
            generated = project / "campus-pet/build"
            generated.mkdir(parents=True)
            (generated / "cache").write_text("generated")
            preview = workspace / release.PREVIEWS[0]
            preview.mkdir()
            (preview / "manifest.json").write_text(json.dumps({"stage": "development-preview"}))
            before = release.baseline_snapshot(workspace)
            release.cleanup_generated(project, workspace)
            self.assertFalse(generated.exists())
            self.assertFalse(preview.exists())
            self.assertEqual(release.baseline_snapshot(workspace), before)
            self.assertTrue(all((workspace / name).is_file() for name in keep))

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
            (project / "campus-pet/build").symlink_to(personal, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "Linked"):
                release.cleanup_generated(project, workspace)
            self.assertTrue(personal.is_dir())
