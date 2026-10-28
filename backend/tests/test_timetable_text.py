"""Real graph/tools/SQLite with an explicit synthetic model, no paid calls."""

import copy
import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent import conversation, student_agent
from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login
from tests.test_timetable_recognition import confirm, edit, reviewed, settings, write


class TextTimetableModel(ToolModel):
    """Fixed fixtures only; this is not a natural-language parser."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = next(
            str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)
        )
        last = messages[-1]
        if not text.startswith(("添加文字课表", "补充第3至8周")):
            return super()._generate(messages, stop, run_manager, **kwargs)
        call = None
        if isinstance(last, ToolMessage):
            result = json.loads(last.content)
            if last.name == "list_timetable_drafts":
                draft = result[0]
                call = {
                    "name": "update_timetable_draft",
                    "args": {
                        "draft_id": draft["id"],
                        "revision": draft["revision"],
                        "candidate_id": draft["data"]["payload"]["candidates"][0][
                            "candidate_id"
                        ],
                        "changes": {"weeks_text": "3-8周"},
                    },
                }
            else:
                questions = result.get("data", {}).get("clarifications", [])
                answer = (
                    "；".join(q["question"] for q in questions)
                    if questions
                    else "已生成课表草稿，请逐门校对确认。"
                )
                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content=answer))]
                )
        elif text.startswith("添加文字课表"):
            call = {
                "name": "create_timetable_draft",
                "args": {
                    "courses": [
                        {"name": "高等数学", "weekday": 1, "periods": [1, 2]},
                        {
                            "name": "大学英语",
                            "weekday": 2,
                            "weeks_text": "1-16周(单)",
                            "periods": [1, 2],
                        },
                    ]
                },
            }
        else:
            call = {"name": "list_timetable_drafts", "args": {}}
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[{**call, "id": str(uuid4()), "type": "tool_call"}],
                    )
                )
            ]
        )


def thread(c, h):
    return write(c, h, "/agent/threads", {}).json()["id"]


def run(c, h, tid, message):
    r = write(c, h, "/agent/runs", {"thread_id": tid, "message": message})
    assert r.status_code == 200, r.text
    result = wait_run(c, r.json()["id"])
    assert result["data"]["status"] == "done", result
    return result


def test_chat_missing_fields_followup_same_draft_proof_and_save(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        c.app.state.agent_model_factory = lambda: TextTimetableModel()
        tid = thread(c, h)
        r = run(
            c,
            h,
            tid,
            "添加文字课表：高等数学每周一1、2节，周次待补；英语周二1、2节，1-16周单周。",
        )
        d = c.get("/api/drafts").json()[0]
        assert c.get("/api/courses").json() == []
        assert d["data"]["payload"]["candidates"][0]["weeks_text"] is None
        assert d["data"]["clarifications"][0]["field"] == "weeks_text"
        assert "第几周开始" in c.get(f"/api/agent/runs/{r['id']}/events").text
        assert d["data"]["source"]["messages"][0]["text"].startswith("添加文字课表")
        assert confirm(c, h, d).status_code == 422
        untouched = copy.deepcopy(d["data"]["payload"]["candidates"][1])
        run(c, h, tid, "补充第3至8周，只改高等数学。")
        drafts = c.get("/api/drafts").json()
        assert len(drafts) == 1 and drafts[0]["id"] == d["id"]
        updated = drafts[0]
        assert updated["revision"] == d["revision"] + 1
        assert updated["data"]["payload"]["candidates"][1] == untouched
        assert len(updated["data"]["source"]["messages"]) == 2
        assert updated["data"]["clarifications"] == []
        assert (
            write(
                c, h, f"/drafts/{d['id']}/confirm", {"revision": d["revision"]}
            ).status_code
            == 409
        )
        d = edit(c, h, updated, reviewed(updated))
        preview = write(
            c,
            h,
            f"/drafts/{d['id']}/timetable-preview",
            {"revision": d["revision"], "payload": d["data"]["payload"]},
        )
        assert preview.json()["added"] == ["高等数学", "大学英语"]
        assert confirm(c, h, d).status_code == 200
        assert confirm(c, h, d).status_code == 200
        courses = c.get("/api/courses").json()
        assert len(courses) == 2
        assert courses[0]["data"]["source_key"].startswith("text:")
        assert sorted(r["data"]["weeks"] for r in courses) == [
            [1, 3, 5, 7, 9, 11, 13, 15],
            [3, 4, 5, 6, 7, 8],
        ]
        assert c.get("/api/tasks").json() == []
        assert c.get("/api/fixed-events").json() == []


def tool_graph(c, owner):
    c.app.state.agent_model_factory = lambda: ToolModel()
    return student_agent(c.app, owner).nodes["tools"].bound.tools_by_name


def invoke(c, tool, args, run_id="synthetic-run"):
    # Explicit local context to exercise retry/version semantics without a model.
    async def call():
        token = conversation.set(
            {
                "run_id": run_id,
                "thread_id": "synthetic-thread",
                "message": "原始用户文字，不由模型填入",
            }
        )
        try:
            return await tool.ainvoke(args)
        finally:
            conversation.reset(token)

    return c.portal.call(call)


def create(c, h, **changes):
    owner = c.get("/api/me").json()["id"]
    tools = tool_graph(c, owner)
    args = {
        "courses": [
            {
                "name": "文字数学",
                "weekday": 1,
                "weeks_text": "1-8周",
                "periods": [1, 2],
                **changes,
            }
        ]
    }
    return invoke(c, tools["create_timetable_draft"], args), tools, args


def test_tool_retry_deduplicates_and_current_owner_is_enforced(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        d, tools, args = create(c, h)
        assert invoke(c, tools["create_timetable_draft"], args)["id"] == d["id"]
        assert len(c.get("/api/drafts").json()) == 1
        assert (
            d["data"]["source"]["messages"][0]["text"] == "原始用户文字，不由模型填入"
        )
        c.post("/api/auth/logout", headers=h)
        register_login(c, "other@example.com")
        other = tool_graph(c, c.get("/api/me").json()["id"])
        assert invoke(c, other["list_timetable_drafts"], {}) == []
        assert c.get(f"/api/drafts/{d['id']}").status_code == 404
        with pytest.raises(Exception) as error:
            invoke(
                c,
                other["update_timetable_draft"],
                {
                    "draft_id": d["id"],
                    "revision": d["revision"],
                    "changes": {"name": "越权"},
                    "candidate_id": d["data"]["payload"]["candidates"][0][
                        "candidate_id"
                    ],
                },
            )
        assert error.value.status_code == 404


def test_patch_preserves_fields_retries_and_stale_version(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        d, tools, _ = create(c, h, teacher="王老师", location="A101")
        candidate = d["data"]["payload"]["candidates"][0]
        args = {
            "draft_id": d["id"],
            "revision": d["revision"],
            "candidate_id": candidate["candidate_id"],
            "changes": {"weeks_text": "3-8周"},
        }
        updated = invoke(c, tools["update_timetable_draft"], args, "followup")
        assert invoke(c, tools["update_timetable_draft"], args, "followup") == updated
        course = updated["data"]["payload"]["candidates"][0]
        assert course["teacher"] == "王老师" and course["location"] == "A101"
        assert course["periods"] == [1, 2]
        assert course["weeks_text"] == "3-8周" and not course["reviewed"]
        with pytest.raises(Exception) as error:
            invoke(c, tools["update_timetable_draft"], args, "another-followup")
        assert error.value.status_code == 409
        original = d["data"]["payload"]["candidates"][0]
        tampered = copy.deepcopy(updated["data"]["payload"])
        tampered["candidates"][0]["candidate_id"] = "fake"
        assert (
            write(
                c,
                h,
                f"/drafts/{d['id']}",
                {"revision": updated["revision"], "payload": tampered},
                "put",
            ).status_code
            == 422
        )
        assert original["weeks_text"] == "1-8周"


@pytest.mark.parametrize(
    "changes",
    [
        {"weeks_text": "几周左右"},
        {"weekday": None},
        {"periods": []},
        {"periods": [1, 3]},
        {"name": "  "},
        {"weeks_text": "1-30周"},
    ],
)
def test_uncertain_or_invalid_courses_cannot_be_saved(tmp_path, changes):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        d, _, _ = create(c, h, **changes)
        assert d["data"]["clarifications"]
        d = edit(c, h, d, reviewed(d))
        assert confirm(c, h, d).status_code == 422
        assert c.get("/api/courses").json() == []


def test_repeat_draft_reuses_exact_course_and_keeps_old_courses(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        old = write(
            c,
            h,
            "/drafts/timetable",
            {
                "semester_label": "2026秋季",
                "courses": [
                    {
                        "source_key": "existing-manual",
                        "name": "已有物理",
                        "weekday": 3,
                        "weeks": [1, 2],
                        "periods": [1, 2],
                    }
                ],
            },
        ).json()
        assert confirm(c, h, old).status_code == 200
        for i in range(2):
            d, tools, args = create(c, h)
            if i:
                # Same tool call in a different user run is a new review intent.
                d = invoke(c, tools["create_timetable_draft"], args, "new-run")
            d = edit(c, h, d, reviewed(d))
            assert confirm(c, h, d).status_code == 200
        saved = c.get("/api/courses").json()
        assert len(saved) == 2
        assert {r["data"]["name"] for r in saved} == {"已有物理", "文字数学"}


def test_confirmed_text_course_cannot_be_patched_as_a_pending_draft(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        d, tools, _ = create(c, h)
        d = edit(c, h, d, reviewed(d))
        assert confirm(c, h, d).status_code == 200
        saved = c.get("/api/courses").json()
        d = c.get(f"/api/drafts/{d['id']}").json()
        with pytest.raises(Exception) as error:
            invoke(
                c,
                tools["update_timetable_draft"],
                {
                    "draft_id": d["id"],
                    "revision": d["revision"],
                    "candidate_id": d["data"]["payload"]["candidates"][0][
                        "candidate_id"
                    ],
                    "changes": {"weekday": 7},
                },
                "after-save",
            )
        assert error.value.status_code == 409
        assert c.get("/api/courses").json() == saved


def test_reboot_keeps_questions_messages_and_reviewable_draft(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        cookies = dict(c.cookies)
        d, _, _ = create(c, h, weeks_text=None)
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        restored = c.get(f"/api/drafts/{d['id']}").json()
        assert restored == d
