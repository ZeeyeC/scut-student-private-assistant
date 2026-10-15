"""Regression coverage for independent drafts and semester-based deadlines."""

import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent import student_agent
from tests.test_agent import ToolModel
from tests.test_assignments import png
from tests.test_calendar_events import post
from tests.test_foundation import make_client, register_login


class AcademicDraftModel(ToolModel):
    """Explicit fixture: actual business tools calculate dates and edit drafts."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1]
        text = next(
            str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)
        )
        calls = []
        if isinstance(last, HumanMessage):
            if "改成" in text:
                calls = [("get_current_time", {})]
            else:
                calls = [
                    ("create_assignment_draft", {"title": title, "due_text": due})
                    for title, due in [
                        ("C++大作业", "第14周之前"),
                        ("agent大作业", "11周之前"),
                    ]
                ]
        elif isinstance(last, ToolMessage) and last.name == "get_current_time":
            calls = [("list_assignment_drafts", {})]
        elif isinstance(last, ToolMessage) and last.name == "list_assignment_drafts":
            drafts = json.loads(last.content)
            draft = next(
                d
                for d in drafts
                if d["data"]["payload"]["items"][0]["title"] == "C++大作业"
            )
            clock = next(
                json.loads(m.content)
                for m in reversed(messages)
                if isinstance(m, ToolMessage) and m.name == "get_current_time"
            )
            calls = [
                (
                    "set_assignment_draft_deadline",
                    {
                        "draft_id": draft["id"],
                        "revision": draft["revision"],
                        "item_index": 0,
                        "due_text": "明天晚上8点",
                        "due_at": clock["tomorrow"] + "T20:00:00+08:00",
                    },
                )
            ]
        message = AIMessage(
            content="草稿已更新，请校对后保存。" if not calls else "",
            tool_calls=[
                {
                    "name": name,
                    "args": args,
                    "id": f"academic-{i}-{name}",
                    "type": "tool_call",
                }
                for i, (name, args) in enumerate(calls)
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def semester(c, h, monday="2026-08-31"):
    s = c.get("/api/settings").json()
    s["data"]["week1_monday"] = monday
    return c.put("/api/settings", json=s, headers={**h, "Idempotency-Key": monday})


def draft(c, h, title, due_text=None):
    r = post(
        c,
        h,
        "/api/drafts/assignment",
        {"items": [{"title": title, "due_text": due_text}]},
        str(uuid4()),
    )
    assert r.status_code == 200, r.text
    return r.json()


def confirm(c, h, d, key):
    return post(
        c, h, f"/api/drafts/{d['id']}/confirm", {"revision": d["revision"]}, key
    )


def test_independent_drafts_can_be_saved_in_sequence_but_edited_version_still_conflicts(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        a, b = draft(c, h, "第一份"), draft(c, h, "第二份")
        assert confirm(c, h, a, "save-a").status_code == 200
        assert confirm(c, h, b, "save-b").status_code == 200
        assert confirm(c, h, b, "replay-b").status_code == 200
        assert len(c.get("/api/tasks").json()) == 2
        d = draft(c, h, "被修改")
        changed = c.put(
            f"/api/drafts/{d['id']}",
            json={"revision": 1, "payload": {"items": [{"title": "新标题"}]}},
            headers={**h, "Idempotency-Key": "edit"},
        )
        assert changed.status_code == 200
        assert confirm(c, h, d, "old-version").status_code == 409
        assert confirm(c, h, changed.json(), "new-version").status_code == 200


def test_week_before_is_exact_boundary_not_an_invented_2359_and_changes_are_guarded(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        assert semester(c, h).status_code == 200
        a = draft(c, h, "C++大作业", "第14周之前")
        b = draft(c, h, "agent大作业", "11周之前")
        item = a["data"]["payload"]["items"][0]
        assert item["due_at"] == "2026-11-30T00:00:00+08:00"
        assert item["deadline_basis"]["week1_monday"] == "2026-08-31"
        assert "due_at" not in item["uncertain_fields"]
        assert b["data"]["payload"]["items"][0]["due_at"] == "2026-11-09T00:00:00+08:00"
        assert confirm(c, h, a, "a").status_code == 200
        assert confirm(c, h, b, "b").status_code == 200
        d = draft(c, h, "学期已改", "第14周之前")
        assert semester(c, h, "2026-09-07").status_code == 200
        assert confirm(c, h, d, "stale-semester").status_code == 409


@pytest.mark.parametrize(
    "text", ["明天", "第14周左右", "第40周之前", "下周五", "第14周周末前"]
)
def test_uncertain_or_out_of_semester_deadline_remains_unresolved(tmp_path, text):
    with make_client(tmp_path) as c:
        h = register_login(c)
        semester(c, h)
        item = draft(c, h, "日期边界", text)["data"]["payload"]["items"][0]
        assert item["due_at"] is None


def test_pending_draft_deadline_tool_preserves_other_items_asset_and_ownership(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        semester(c, h)
        asset = c.post(
            "/api/assets",
            files={"file": ("fixture.png", png(), "image/png")},
            headers={**h, "Idempotency-Key": "image"},
        ).json()
        d = post(
            c,
            h,
            "/api/drafts/assignment",
            {
                "asset_id": asset["id"],
                "items": [
                    {"title": "C++", "requirements": ["提交源码"]},
                    {"title": "agent"},
                ],
            },
            "multi",
        ).json()
        owner = c.get("/api/me").json()["id"]
        c.app.state.agent_model_factory = lambda: ToolModel()
        tools = student_agent(c.app, owner).nodes["tools"].bound.tools_by_name
        assert "list_assignment_drafts" in tools
        args = {
            "draft_id": d["id"],
            "revision": 1,
            "item_index": 0,
            "due_text": "第14周之前",
            "due_at": None,
        }
        edited = c.portal.call(tools["set_assignment_draft_deadline"].ainvoke, args)
        assert edited["id"] == d["id"] and edited["revision"] == 2
        assert edited["data"]["payload"]["asset_id"] == asset["id"]
        assert edited["data"]["payload"]["items"][0]["requirements"] == ["提交源码"]
        assert edited["data"]["payload"]["items"][1]["title"] == "agent"
        assert (
            edited["data"]["payload"]["items"][0]["due_at"]
            == "2026-11-30T00:00:00+08:00"
        )
        assert c.get("/api/tasks").json() == []
        assert (
            c.portal.call(tools["set_assignment_draft_deadline"].ainvoke, args)
            == edited
        )
        with pytest.raises(HTTPException) as stale:
            c.portal.call(
                tools["set_assignment_draft_deadline"].ainvoke,
                {**args, "due_text": "11周之前"},
            )
        assert stale.value.status_code == 409
        c.post("/api/auth/logout", headers=h)
        register_login(c, "other@example.com")
        stranger = c.get("/api/me").json()["id"]
        stranger_tools = (
            student_agent(c.app, stranger).nodes["tools"].bound.tools_by_name
        )
        with pytest.raises(HTTPException) as denied:
            c.portal.call(
                stranger_tools["set_assignment_draft_deadline"].ainvoke,
                {**args, "revision": 2},
            )
        assert denied.value.status_code == 404


def test_legacy_preview_suggests_dates_without_mutating_or_saving_a_task(tmp_path):
    from copy import deepcopy

    from app import store
    from app.agent import transaction

    with make_client(tmp_path) as c:
        h = register_login(c)
        semester(c, h)
        d = draft(c, h, "旧版草稿", "第14周之前")
        owner = c.get("/api/me").json()["id"]

        async def legacy(read=False):
            async with transaction(c.app) as db:
                r = await store.owned(db, owner, d["id"], "draft")
                if not read:
                    data = deepcopy(r.data)
                    data["payload"]["items"][0].update(
                        due_at=None, deadline_basis=None, uncertain_fields=["due_at"]
                    )
                    r.data = data
                return store.view(r)

        original = c.portal.call(legacy)
        preview = c.get(f"/api/drafts/{d['id']}").json()
        assert preview["data"]["payload"]["items"][0]["due_at"] is None
        assert (
            preview["data"]["suggested_payload"]["items"][0]["due_at"]
            == "2026-11-30T00:00:00+08:00"
        )
        assert c.portal.call(legacy, True) == original
        edited = c.put(
            f"/api/drafts/{d['id']}",
            json={
                "revision": original["revision"],
                "payload": preview["data"]["suggested_payload"],
            },
            headers={**h, "Idempotency-Key": "apply-preview"},
        ).json()
        assert confirm(c, h, edited, "save-legacy").status_code == 200
        assert (
            c.get("/api/tasks").json()[0]["data"]["due_at"]
            == "2026-11-30T00:00:00+08:00"
        )
