"""Check the packaged PDF decoder using an isolated temporary local profile.

Refuses an occupied port and verifies database identity before any API writes.
No personal files or model calls. Stops only the child process it created.
"""

import argparse
import http.cookiejar
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.launcher import desktop_config, service_identity
from pypdf import PdfWriter


def verify(service):
    origin = "http://127.0.0.1:5173"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    try:
        opener.open(origin + "/api/healthz", timeout=1)
    except urllib.error.HTTPError:
        raise SystemExit("5173 occupied; nothing started or changed.") from None
    except urllib.error.URLError:
        pass
    else:
        raise SystemExit("5173 occupied; nothing started or changed.")
    with tempfile.TemporaryDirectory(prefix="campus-frozen-pdf-") as temporary:
        root = Path(temporary)
        expected = service_identity(desktop_config(root, root, project=False))
        with (root / "server.log").open("w") as log:
            process = subprocess.Popen(
                [str(service), "--serve", "--no-browser", "--data-dir", str(root)],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Frozen backend startup failed; temporary log retained only until exit."
                        )
                    try:
                        health = json.load(
                            opener.open(origin + "/api/healthz", timeout=1)
                        )
                        if any(health.get(k) != v for k, v in expected.items()):
                            raise RuntimeError(
                                "Different service identity; no writes performed."
                            )
                        assert health["model_configured"] is False
                        assert "timetable-recognition" in health["capabilities"]
                        assert "timetable-text" in health["capabilities"]
                        assert "planning-today" in health["capabilities"]
                        assert "course-changes" in health["capabilities"]
                        break
                    except urllib.error.URLError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Frozen backend did not start.")
                csrf = json.load(opener.open(origin + "/api/csrf"))["csrf_token"]

                def request(path, body, content_type="application/json", method="POST"):
                    headers = {
                        "Origin": origin,
                        "X-CSRF-Token": csrf,
                        "Idempotency-Key": str(uuid4()),
                        "Content-Type": content_type,
                    }
                    return opener.open(
                        urllib.request.Request(
                            origin + "/api" + path,
                            data=body,
                            headers=headers,
                            method=method,
                        ),
                        timeout=30,
                    )

                request("/local/session", b"{}").read()

                def write_json(path, body, method="POST"):
                    return json.load(
                        request(path, json.dumps(body).encode(), method=method)
                    )

                # Exercise new domain modules inside the actual PyInstaller binary.
                local_day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                settings = json.load(opener.open(origin + "/api/settings"))
                settings["data"].update(
                    timezone="Asia/Shanghai",
                    week1_monday=(
                        local_day - timedelta(days=local_day.weekday())
                    ).isoformat(),
                    periods={"1": {"start": "09:00", "end": "10:00"}},
                )
                write_json("/settings", settings, "PUT")
                course_draft = write_json(
                    "/drafts/timetable",
                    {
                        "semester_label": "synthetic frozen check",
                        "courses": [
                            {
                                "source_key": "frozen-course",
                                "name": "冻结包合成课程",
                                "weekday": local_day.isoweekday(),
                                "weeks": [1],
                                "periods": [1],
                            }
                        ],
                    },
                )
                saved = write_json(
                    f"/drafts/{course_draft['id']}/confirm",
                    {"revision": course_draft["revision"]},
                )
                cid = saved["saved_ids"][0]
                query = f"/api/occurrences?start={local_day}&end={local_day + timedelta(days=1)}"
                original = json.load(opener.open(origin + query))
                tomorrow = local_day + timedelta(days=1)
                for action in ("move", "cancel", "restore"):
                    payload = {
                        "course_id": cid,
                        "original_date": local_day.isoformat(),
                        "action": action,
                        "reason": "合成测试通知",
                    }
                    if action == "move":
                        payload.update(
                            starts_at=f"{tomorrow}T10:00:00+08:00",
                            ends_at=f"{tomorrow}T11:00:00+08:00",
                        )
                    draft = write_json("/drafts/course-change", payload)
                    write_json(
                        f"/drafts/{draft['id']}/confirm",
                        {"revision": draft["revision"]},
                    )
                    events = json.load(opener.open(origin + query))
                    if action == "move":
                        assert events[0]["starts_at"].startswith(str(tomorrow))
                    elif action == "cancel":
                        assert events == []
                    else:
                        assert events == original
                assert (
                    len(json.load(opener.open(origin + "/api/course-change-history")))
                    == 3
                )
                plan = write_json("/plan-drafts", {"scope": "today"})
                assert plan["data"]["payload"]["target_date"] == str(local_day)
                assert plan["data"]["payload"]["horizon_days"] == 1
                assert json.load(opener.open(origin + "/api/plan-blocks")) == []
                writer = PdfWriter()
                writer.add_blank_page(width=500, height=700)
                pdf = BytesIO()
                writer.write(pdf)
                boundary = "test-" + uuid4().hex
                multipart = (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
                    + pdf.getvalue()
                    + f"\r\n--{boundary}--\r\n".encode()
                )
                asset = json.load(
                    request(
                        "/timetable-assets",
                        multipart,
                        "multipart/form-data; boundary=" + boundary,
                    )
                )
                assert asset["data"]["pages"][0]["type"] == "scanned_pdf"
                image = opener.open(
                    origin + f"/api/assets/{asset['id']}/pages/1"
                ).read()
                assert image.startswith(b"\x89PNG")
                exported = json.load(opener.open(origin + "/api/data-export"))
                assert len(exported["asset_files_base64"]) == 2
                assert (
                    request(
                        "/data-delete",
                        json.dumps({"confirmation": "删除我的所有数据"}).encode(),
                    ).status
                    == 200
                )
                assert list((root / "data/uploads").iterdir()) == []
                return {
                    "passed": True,
                    "scope": "actual frozen backend, temporary local profile, no model calls",
                    "checks": [
                        "isolated database identity",
                        "frozen today planner creates review-only one-day draft",
                        "frozen course move, cancel, restore and audit history",
                        "PDFium dynamic library loads",
                        "PDF upload and render",
                        "page PNG served",
                        "original and page export",
                        "asset cleanup",
                    ],
                }
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.service.resolve())
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
