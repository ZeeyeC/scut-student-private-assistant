from fastapi.testclient import TestClient

from tests.test_browser_import import configured_client
from tests.test_foundation import register_login

TOKEN = "a" * 64


def start(c, headers):
    r = c.post("/api/browser-imports", json={"school_id": "scut"}, headers={**headers, "Idempotency-Key": "desktop-start"})
    assert r.status_code == 200
    return r.json()


def issue(c, headers, session):
    r = c.post(f"/api/browser-imports/{session['id']}/desktop-grant", json={"client_token": TOKEN}, headers={**headers, "Idempotency-Key": "grant-issue"})
    assert r.status_code == 200
    return r.json()


def bridge_client(c, grant):
    browser = TestClient(c.app)
    csrf = browser.get("/api/csrf").json()["csrf_token"]
    headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf, "Authorization": f"Bearer {grant['grant_id']}.{TOKEN}"}
    return browser, headers


def test_grant_is_scoped_and_stores_no_plain_token(tmp_path):
    with configured_client(tmp_path) as c:
        h = register_login(c)
        session = start(c, h)
        grant = issue(c, h, session)
        assert grant["expires_at"] <= session["data"]["expires_at"]
        browser, bh = bridge_client(c, grant)
        url = f"/api/desktop-import-bridge/{session['id']}"
        assert browser.get(url, headers=bh).json()["session"]["id"] == session["id"]
        assert browser.get("/api/tasks", headers=bh).status_code == 401
        assert browser.get(url, headers={**bh, "Authorization": "Bearer invalid"}).status_code == 401
        assert browser.get("/api/desktop-import-bridge/another-import", headers=bh).status_code == 404
        assert TOKEN not in c.get("/api/data-export").text
        assert browser.post(url + "/bridge-state", json={"state": "ready"}, headers={"Origin": "http://testserver", "Authorization": bh["Authorization"]}).status_code == 403
        assert browser.post(url + "/bridge-state", json={"state": "extension_missing"}, headers={**bh, "Idempotency-Key": "missing"}).status_code == 200
        assert c.get(f"/api/browser-imports/{session['id']}").json()["data"]["desktop_bridge_status"] == "extension_missing"


def test_capture_consumes_grant_only_exact_operation_can_replay_and_app_confirms(tmp_path):
    with configured_client(tmp_path) as c:
        h = register_login(c)
        session = start(c, h)
        grant = issue(c, h, session)
        browser, bh = bridge_client(c, grant)
        url = f"/api/desktop-import-bridge/{session['id']}"
        current = session
        for kind in ["opened", "waiting_timetable", "extracting"]:
            r = browser.post(url + "/events", json={"kind": kind, "event_id": kind, "revision": current["revision"]}, headers={**bh, "Idempotency-Key": kind})
            assert r.status_code == 200
            current = r.json()
        payload = {"revision": current["revision"], "adapter_version": "test-fixture-v1", "school_origin": "https://fixture.scut.edu.cn", "semester_label": "合成学期", "fragments": ["<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th></tr><tr><td>合成数学</td><td>1</td><td>1-8</td><td>1-2</td><td>A101</td></tr></table>"]}
        r = browser.post(url + "/capture", json=payload, headers={**bh, "Idempotency-Key": "capture-once"})
        assert r.status_code == 200
        draft = r.json()
        assert browser.post(url + "/capture", json=payload, headers={**bh, "Idempotency-Key": "capture-once"}).json() == draft
        assert browser.post(url + "/capture", json=payload, headers={**bh, "Idempotency-Key": "another-operation"}).status_code == 409
        assert browser.post(url + "/capture", json={**payload, "semester_label": "不同内容"}, headers={**bh, "Idempotency-Key": "capture-once"}).status_code == 409
        assert c.get("/api/courses").json() == []
        assert browser.post(f"/api/drafts/{draft['id']}/confirm", json={"revision": draft["revision"]}, headers={**bh, "Idempotency-Key": "browser-cannot-confirm"}).status_code == 401
        assert c.post(f"/api/drafts/{draft['id']}/confirm", json={"revision": draft["revision"]}, headers={**h, "Idempotency-Key": "app-confirm"}).status_code == 200
        assert len(c.get("/api/courses").json()) == 1


def test_cancel_revokes_even_capture_receipts_and_other_owners_cannot_issue(tmp_path):
    with configured_client(tmp_path) as c:
        h = register_login(c)
        session = start(c, h)
        grant = issue(c, h, session)
        browser, bh = bridge_client(c, grant)
        r = c.post(f"/api/browser-imports/{session['id']}/cancel", json={"revision": session["revision"]}, headers={**h, "Idempotency-Key": "cancel"})
        assert r.status_code == 200
        assert browser.get(f"/api/desktop-import-bridge/{session['id']}", headers=bh).status_code == 410
        c.cookies.clear()
        other = register_login(c, "second-owner@example.com")
        assert c.post(f"/api/browser-imports/{session['id']}/desktop-grant", json={"client_token": TOKEN}, headers={**other, "Idempotency-Key": "wrong-owner"}).status_code == 404
