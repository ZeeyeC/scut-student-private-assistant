"""Stable resources in source checkouts and frozen desktop bundles."""

import os
import sys
from pathlib import Path


def resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def user_data_dir():
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CampusCompanion"
    if sys.platform == "win32":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "CampusCompanion"
        )
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "campus-companion"
    )
