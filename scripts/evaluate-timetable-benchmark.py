#!/usr/bin/env python3
"""Score a local annotation manifest; never load images or call a model."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.timetable_benchmark import evaluate_manifest, render_markdown


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="local v1 JSON annotation manifest")
    parser.add_argument(
        "--output", required=True, type=Path, help="JSON aggregate report"
    )
    parser.add_argument(
        "--markdown", type=Path, help="optional aggregate Markdown report"
    )
    args = parser.parse_args(argv)
    paths = [args.manifest, args.output] + ([args.markdown] if args.markdown else [])
    if len({path.resolve() for path in paths}) != len(paths):
        print("error: input and report paths must be distinct", file=sys.stderr)
        return 1
    try:
        with args.manifest.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        report = evaluate_manifest(manifest)
        encoded = (
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        markdown = render_markdown(report) if args.markdown else None
        args.output.write_text(encoded, encoding="utf-8")
        if args.markdown:
            args.markdown.write_text(markdown, encoding="utf-8")
    except json.JSONDecodeError:
        print("error: invalid JSON manifest", file=sys.stderr)
        return 1
    except ValueError as error:
        # Our validator only emits schema paths/reasons, not submitted values.
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError):
        print(
            "error: manifest could not be read or report could not be written",
            file=sys.stderr,
        )
        return 1
    print(f"status={report['status']} passed={str(report['passed']).lower()}")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
