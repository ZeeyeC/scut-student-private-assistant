"""Natural-language candidates use real constraint drafts, never default hours."""

import json
from datetime import datetime

from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import resources, write


def client(tmp_path, monkeypatch, clock="2026-10-14T08:00:00+08:00"):
    from app import conversation_constraints as domain

    monkeypatch.setattr(domain, "now", lambda: datetime.fromisoformat(clock))
    return make_client(tmp_path)


def post(c, h, path, body, method="POST", key=None):
    r = write(c, h, path, body, method, key=key)
    assert r.status_code == 200, r.text
    return r.json()


def test_clarification_same_draft_and_private_reason_not_repeated(
    tmp_path, monkeypatch
):
    with client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        intent = post(
            c,
            h,
            "/constraint-intents",
            {"data": {"day_expression": "这周三下午去医院"}},
        )
        assert intent["data"]["fields"]["day_expression"] == "2026-10-14"
        assert intent["data"]["clarifications"]
        assert "医院" not in json.dumps(intent, ensure_ascii=False)
        assert not resources(c, "draft") and not resources(c, "scheduling_constraint")
        intent = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}",
            {
                "revision": intent["revision"],
                "changes": {"start_time": "14:00", "end_time": "17:00"},
            },
            "PATCH",
        )
        first = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}/prepare",
            {"revision": intent["revision"]},
            key="prepare",
        )
        assert (
            post(
                c,
                h,
                f"/constraint-intents/{intent['id']}/prepare",
                {"revision": intent["revision"]},
                key="prepare",
            )
            == first
        )
        d = first["draft"]
        assert d["data"]["payload"]["constraint"]["title"] == "不可安排"
        assert not resources(c, "scheduling_constraint")
        updated = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}",
            {"revision": first["revision"], "changes": {"end_time": "18:00"}},
            "PATCH",
        )
        assert updated["draft"]["id"] == d["id"]
        assert (
            write(
                c, h, f"/drafts/{d['id']}/confirm", {"revision": d["revision"]}
            ).status_code
            == 409
        )
        post(
            c,
            h,
            f"/drafts/{d['id']}/confirm",
            {"revision": updated["draft"]["revision"]},
        )
        assert len(resources(c, "scheduling_constraint")) == 1
        saved = c.get(f"/api/constraint-intents/{intent['id']}").json()
        assert saved["data"]["status"] == "confirmed"
        assert "医院" not in json.dumps(
            resources(c, "scheduling_constraint"), ensure_ascii=False
        )


def test_cancel_confirmed_requires_explicit_rule_disable_and_persists(
    tmp_path, monkeypatch
):
    with client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        intent = post(
            c,
            h,
            "/constraint-intents",
            {
                "data": {
                    "day_expression": "这周三",
                    "start_time": "14:00",
                    "end_time": "17:00",
                }
            },
        )
        intent = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}/prepare",
            {"revision": intent["revision"]},
        )
        post(
            c,
            h,
            f"/drafts/{intent['draft']['id']}/confirm",
            {"revision": intent["draft"]["revision"]},
        )
        request = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}/cancel",
            {"revision": intent["revision"]},
        )
        rule = request["constraint"]
        assert rule["data"]["active"] is True
        post(
            c,
            h,
            f"/scheduling-constraints/{rule['id']}",
            {"revision": rule["revision"], "active": False},
            "PATCH",
        )
        cookie = dict(c.cookies)
    with client(tmp_path, monkeypatch) as c:
        c.cookies.update(cookie)
        restored = c.get(f"/api/constraint-intents/{intent['id']}").json()
        assert restored["data"]["status"] == "disabled"
        assert not restored["constraint"]["data"]["active"]


def test_relative_week_crosses_year_and_uses_message_timezone(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, "2026-12-31T23:00:00+08:00") as c:
        h = register_login(c)
        intent = post(
            c,
            h,
            "/constraint-intents",
            {
                "data": {
                    "day_expression": "下周开始每周五晚上",
                    "start_time": "19:00",
                    "end_time": "21:00",
                    "recurrence": "weekly",
                }
            },
        )
        assert intent["data"]["fields"]["day_expression"] == "2027-01-08"
        d = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}/prepare",
            {"revision": intent["revision"]},
        )["draft"]
        p = d["data"]["payload"]["constraint"]
        assert p["weekdays"] == [5] and p["recurrence"] == "weekly"
    with client(tmp_path / "west", monkeypatch, "2027-01-04T02:00:00+00:00") as c:
        h = register_login(c)
        settings = c.get("/api/settings").json()
        settings["data"]["timezone"] = "America/Los_Angeles"
        post(c, h, "/settings", settings, "PUT")
        intent = post(
            c,
            h,
            "/constraint-intents",
            {
                "data": {
                    "day_expression": "下周一",
                    "start_time": "14:00",
                    "end_time": "17:00",
                }
            },
        )
        assert intent["data"]["fields"]["day_expression"] == "2027-01-04"


def test_ownership_revision_replay_and_cancellation(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        payload = {"data": {"day_expression": "这周三"}}
        intent = post(c, h, "/constraint-intents", payload, key="create")
        assert post(c, h, "/constraint-intents", payload, key="create") == intent
        assert (
            write(
                c,
                h,
                "/constraint-intents",
                {"data": {"day_expression": "明天"}},
                key="create",
            ).status_code
            == 409
        )
        changed = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}",
            {"revision": intent["revision"], "changes": {"start_time": "14:00"}},
            "PATCH",
        )
        assert (
            write(
                c,
                h,
                f"/constraint-intents/{intent['id']}",
                {"revision": intent["revision"], "changes": {"end_time": "17:00"}},
                "PATCH",
            ).status_code
            == 409
        )
        canceled = post(
            c,
            h,
            f"/constraint-intents/{intent['id']}/cancel",
            {"revision": changed["revision"]},
        )
        assert canceled["data"]["status"] == "cancelled" and not resources(
            c, "scheduling_constraint"
        )
        c.post("/api/auth/logout", headers=h)
        register_login(c, "bob@example.com")
        assert c.get(f"/api/constraint-intents/{intent['id']}").status_code == 404


def test_incomplete_or_ambiguous_clocks_never_create_a_rule(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        for values in (
            {"day_expression": "以后有空时"},
            {"day_expression": "今天", "start_time": "22:00", "end_time": "01:00"},
        ):
            i = post(c, h, "/constraint-intents", {"data": values})
            assert i["data"]["clarifications"]
            assert (
                write(
                    c,
                    h,
                    f"/constraint-intents/{i['id']}/prepare",
                    {"revision": i["revision"]},
                ).status_code
                == 409
            )
        assert not resources(c, "draft") and not resources(c, "scheduling_constraint")


def test_invalid_patch_is_a_client_error_and_does_not_lock_editing(
    tmp_path, monkeypatch
):
    with client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        intent = post(
            c, h, "/constraint-intents", {"data": {"day_expression": "这周三"}}
        )
        for changes in (
            {"start_time": "bad"},
            {"timezone": "Mars/Unknown"},
            {"reason": "private"},
        ):
            r = write(
                c,
                h,
                f"/constraint-intents/{intent['id']}",
                {"revision": intent["revision"], "changes": changes},
                "PATCH",
            )
            assert r.status_code == 422
            assert (
                c.get(f"/api/constraint-intents/{intent['id']}").json()["revision"]
                == intent["revision"]
            )


def test_clearing_timezone_uses_settings_without_losing_original_date(
    tmp_path, monkeypatch
):
    with client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        i = post(
            c,
            h,
            "/constraint-intents",
            {
                "data": {
                    "day_expression": "这周三",
                    "start_time": "14:00",
                    "end_time": "17:00",
                    "timezone": "America/Los_Angeles",
                }
            },
        )
        changed = post(
            c,
            h,
            f"/constraint-intents/{i['id']}",
            {
                "revision": i["revision"],
                "changes": {"timezone": None},
            },
            "PATCH",
        )
        assert changed["data"]["fields"]["timezone"] == "Asia/Shanghai"
        assert (
            changed["data"]["fields"]["day_expression"]
            == i["data"]["fields"]["day_expression"]
        )
        assert changed["data"]["reference_date"] == i["data"]["reference_date"]
