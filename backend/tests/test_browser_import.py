import json

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_foundation import register_login


def configured_client(tmp_path):
    adapter = tmp_path / "adapter.json"
    adapter.write_text(
        json.dumps(
            {
                "version": "test-fixture-v1",
                "verified": True,
                "entry_url": "https://fixture.scut.edu.cn/",
                "school_origin": "https://fixture.scut.edu.cn",
                "container_selector": "#fixture-timetable",
                "semester_selector": "#semester",
                "loading_selector": ".loading",
                "columns": {
                    "name": "课程",
                    "weekday": "星期",
                    "weeks": "周次",
                    "periods": "节次",
                    "location": "地点",
                },
                "full_capture": False,
            }
        )
    )
    return TestClient(
        create_app(
            {
                "database_url": f"sqlite+aiosqlite:///{tmp_path}/test.db",
                "agent_db_path": str(tmp_path / "agent.db"),
                "upload_dir": str(tmp_path / "uploads"),
                "public_origin": "http://testserver",
                "scut_adapter_path": str(adapter),
                "secure_cookie": False,
                "app_mode": "shared",
            }
        )
    )


def test_state_receipts_capture_and_confirm(tmp_path):
    with configured_client(tmp_path) as c:
        h = register_login(c)
        h = {**h, "Idempotency-Key": "start"}
        r = c.post("/api/browser-imports", json={"school_id": "scut"}, headers=h)
        assert r.status_code == 200
        b = r.json()
        assert b["data"]["status"] == "queued"
        assert b["data"]["browser_opened_at"] is None
        url = "/api/browser-imports/" + b["id"]
        assert (
            c.post(
                url + "/events",
                json={"kind": "completed", "event_id": "bad", "revision": 1},
                headers=h,
            ).status_code
            == 422
        )
        event = {"kind": "opened", "event_id": "open", "revision": 1}
        opened = c.post(
            url + "/events", json=event, headers={**h, "Idempotency-Key": "opened"}
        ).json()
        assert opened["data"]["browser_opened_at"]
        assert (
            c.post(
                url + "/events", json=event, headers={**h, "Idempotency-Key": "opened2"}
            ).json()
            == opened
        )
        for kind in ["waiting_timetable", "extracting"]:
            opened = c.post(
                url + "/events",
                json={"kind": kind, "event_id": kind, "revision": opened["revision"]},
                headers={**h, "Idempotency-Key": kind},
            ).json()
        capture = {
            "revision": opened["revision"],
            "adapter_version": "test-fixture-v1",
            "school_origin": "https://fixture.scut.edu.cn",
            "semester_label": "测试学期",
            "fragments": [
                "<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th></tr><tr><td>数学</td><td>1</td><td>1-8周(单)</td><td>1-2</td><td>A101</td></tr></table>"
            ],
        }
        d = c.post(
            url + "/capture", json=capture, headers={**h, "Idempotency-Key": "cap"}
        ).json()
        assert d["data"]["payload"]["courses"][0]["weeks"] == [1, 3, 5, 7]
        assert (
            c.post(
                url + "/capture",
                json={**capture, "semester_label": "不同学期"},
                headers={**h, "Idempotency-Key": "cap"},
            ).status_code
            == 409
        )
        assert (
            c.post(
                url + "/capture", json=capture, headers={**h, "Idempotency-Key": "cap2"}
            ).json()["id"]
            == d["id"]
        )
        assert c.get(url).json()["data"]["status"] == "preview_ready"
        assert (
            c.post(
                f"/api/drafts/{d['id']}/confirm",
                json={"revision": 1},
                headers={**h, "Idempotency-Key": "confirm"},
            ).status_code
            == 200
        )
        assert c.get(url).json()["data"]["status"] == "completed"
        assert (
            c.post(
                url + "/events",
                json={"kind": "failed", "event_id": "late", "revision": 5},
                headers={**h, "Idempotency-Key": "late"},
            ).status_code
            == 409
        )


def test_unverified_school_disabled_and_no_arbitrary_url(tmp_path):
    from tests.test_foundation import make_client

    with make_client(tmp_path) as c:
        h = register_login(c)
        assert (
            c.post(
                "/api/browser-imports",
                json={"school_id": "scut"},
                headers={**h, "Idempotency-Key": "s"},
            ).status_code
            == 503
        )
        assert (
            c.post(
                "/api/browser-imports",
                json={"school_id": "other", "url": "https://example.com"},
                headers={**h, "Idempotency-Key": "x"},
            ).status_code
            == 422
        )


def test_parser_rejects_private_and_oversized_fragments(tmp_path):
    import pytest

    from app.browser_imports import parse_capture

    adapter = {
        "columns": {
            "name": "课程",
            "weekday": "星期",
            "weeks": "周次",
            "periods": "节次",
        },
        "full_capture": False,
    }
    for html in [
        '<table><input type="password" value="secret"></table>',
        "<table><script>alert(1)</script></table>",
        "x" * 1048577,
    ]:
        with pytest.raises(ValueError):
            parse_capture([html], adapter, 20)
