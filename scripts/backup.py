"""Offline consistent backup/restore. Run with the project's Python environment."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.backup import backup, restore
from app.config import Config

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="command", required=True)
b = sub.add_parser("backup")
b.add_argument("output", type=Path)
r = sub.add_parser("restore")
r.add_argument("package", type=Path)
r.add_argument("empty_directory", type=Path)
args = parser.parse_args()
if args.command == "backup":
    config = Config()
    backup(
        Path(config.database_url.split("///", 1)[1]),
        config.agent_db_path,
        config.upload_dir,
        args.output,
    )
else:
    restore(args.package, args.empty_directory)
