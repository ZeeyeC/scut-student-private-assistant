from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login


def post(c, h, url, body, key):
    return c.post(url, json=body, headers={**h, "Idempotency-Key": key})


def test_event_draft_confirm_replay_stale_and_owner(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        payload = {
            "title": "彩排",
            "starts_at": "2026-10-16T17:30:00+08:00",
            "ends_at": "2026-10-16T19:00:00+08:00",
        }
        response = post(c, h, "/api/drafts/calendar-event", payload, "draft")
        assert response.status_code == 200
        draft = response.json()
        assert c.get("/api/fixed-events").json() == []
        bad = post(
            c,
            h,
            "/api/drafts/calendar-event",
            {**payload, "ends_at": payload["starts_at"]},
            "bad",
        )
        assert bad.status_code == 422
        url = f"/api/drafts/{draft['id']}/confirm"
        assert (
            post(c, h, url, {"revision": draft["revision"] + 1}, "stale").status_code
            == 409
        )
        for key in ["save", "again"]:
            assert (
                post(c, h, url, {"revision": draft["revision"]}, key).status_code == 200
            )
        assert len(c.get("/api/fixed-events").json()) == 1
        schedule = c.get("/api/calendar-events?start=2026-10-16&end=2026-10-16").json()
        assert len(schedule["events"]) == 1
        assert schedule["events"][0]["title"] == "彩排"
        assert schedule["events"][0]["kind"] == "fixed_event"
        assert (
            c.get("/api/calendar-events?start=2026-10-17&end=2026-10-17").json()[
                "events"
            ]
            == []
        )
        c.post("/api/auth/logout", headers=h)
        register_login(c, "other@example.com")
        assert c.get(f"/api/drafts/{draft['id']}").status_code == 404
        assert (
            c.get("/api/calendar-events?start=2026-10-16&end=2026-10-16").json()[
                "events"
            ]
            == []
        )


def test_empty_plans_explain_pending_tasks_and_replace_pending_proposals(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        draft = post(
            c, h, "/api/drafts/assignment", {"items": [{"title": "阅读文献"}]}, "t"
        ).json()
        post(
            c,
            h,
            f"/api/drafts/{draft['id']}/confirm",
            {"revision": draft["revision"]},
            "save",
        )
        first = post(c, h, "/api/plan-drafts", {}, "plan1").json()
        result = post(c, h, "/api/plan-drafts", {}, "plan2").json()
        assert result["data"]["payload"]["unscheduled"][0]["title"] == "阅读文献"
        drafts = c.get("/api/drafts").json()
        assert [d["id"] for d in drafts if d["data"]["draft_kind"] == "plan"] == [
            result["id"]
        ]
        assert (
            c.get(f"/api/drafts/{first['id']}").json()["data"]["status"] == "superseded"
        )


class CalendarModel(ToolModel):
    """Explicit test-only event tool caller; never a production model."""

    event_args: dict | None = None

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            message = AIMessage(content="已生成日程草稿，请校对确认。")
        else:
            tomorrow = (
                (
                    datetime.now(ZoneInfo("Asia/Shanghai"))
                    + timedelta(days=14 if "两周" in str(messages[-1].content) else 1)
                )
                .date()
                .isoformat()
            )
            args = self.event_args or {
                "title": "参加院运会彩排",
                "starts_at": tomorrow + "T17:30:00+08:00",
                "ends_at": tomorrow + "T19:00:00+08:00",
            }
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_calendar_event_draft",
                        "args": args,
                        "id": "event-1",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_agent_event_correction_updates_one_draft_and_requires_current_revision(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        model = CalendarModel()
        c.app.state.agent_model_factory = lambda: model
        thread = post(c, h, "/api/agent/threads", {}, "thread").json()

        def run(message, key):
            r = post(
                c,
                h,
                "/api/agent/runs",
                {"thread_id": thread["id"], "message": message},
                key,
            ).json()
            assert wait_run(c, r["id"])["data"]["status"] == "done"
            assert "draft_ready" in c.get(f"/api/agent/runs/{r['id']}/events").text

        run("明天下午5:30到7:00参加彩排", "first")
        original = c.get("/api/drafts").json()[0]
        model.event_args = {
            **original["data"]["payload"],
            "ends_at": original["data"]["payload"]["ends_at"].replace("19:00", "19:30"),
            "draft_id": original["id"],
            "revision": original["revision"],
        }
        run("结束时间改成7:30", "second")
        drafts = c.get("/api/drafts").json()
        assert len(drafts) == 1 and drafts[0]["revision"] == original["revision"] + 1
        assert c.get("/api/fixed-events").json() == []
        url = f"/api/drafts/{original['id']}/confirm"
        assert (
            post(c, h, url, {"revision": original["revision"]}, "old").status_code
            == 409
        )
        assert (
            post(c, h, url, {"revision": drafts[0]["revision"]}, "new").status_code
            == 200
        )
        assert "19:30" in c.get("/api/fixed-events").json()[0]["data"]["ends_at"]


def test_course_configuration_warning_does_not_hide_fixed_events(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        post(
            c,
            h,
            "/api/fixed-events",
            {
                "title": "夜间事项",
                "starts_at": "2026-10-15T23:30:00+08:00",
                "ends_at": "2026-10-16T01:00:00+08:00",
            },
            "event",
        )
        draft = post(
            c,
            h,
            "/api/drafts/timetable",
            {
                "semester_label": "测试",
                "courses": [
                    {
                        "source_key": "test",
                        "name": "缺少钟点的课程",
                        "weekday": 1,
                        "weeks": [1],
                        "periods": [1],
                    }
                ],
            },
            "course",
        ).json()
        post(
            c,
            h,
            f"/api/drafts/{draft['id']}/confirm",
            {"revision": draft["revision"]},
            "save",
        )
        result = c.get("/api/calendar-events?start=2026-10-16&end=2026-10-16").json()
        assert result["warnings"]
        assert [e["title"] for e in result["events"]] == ["夜间事项"]
        assert (
            c.get("/api/calendar-events?start=2026-10-16&end=2026-10-15").status_code
            == 422
        )


class DeleteFixedEventModel(ToolModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        import json

        last = messages[-1]
        if isinstance(last, ToolMessage) and last.name == "delete_fixed_event":
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="操作结束"))])
        if isinstance(last, ToolMessage) and last.name == "list_calendar_events":
            event = json.loads(last.content)["events"][0]
            name, args = "delete_fixed_event", {"event_id": event["id"], "revision": event["revision"]}
        else:
            name, args = "list_calendar_events", {"start_date": "2026-10-16", "end_date": "2026-10-16"}
        message = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}])
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_fixed_event_delete_requires_approval(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        event = post(c, h, "/api/fixed-events", {
            "title": "测试事项", "starts_at": "2026-10-16T17:30:00+08:00",
            "ends_at": "2026-10-16T19:00:00+08:00",
        }, "fixed").json()
        url = f"/api/fixed-events/{event['id']}"
        c.app.state.agent_model_factory = DeleteFixedEventModel
        for choice in ("reject", "approve"):
            thread = post(c, h, "/api/agent/threads", {}, f"thread-{choice}").json()
            run = post(c, h, "/api/agent/runs", {
                "thread_id": thread["id"], "message": "删除测试事项",
            }, f"run-{choice}").json()
            pending = wait_run(c, run["id"])
            assert pending["data"]["status"] == "waiting_approval"
            assert c.get(url).json() == event
            approval_id = pending["data"]["approval_id"]
            approval = c.get(f"/api/agent/approvals/{approval_id}").json()
            assert approval["data"]["actions"] == [{
                "name": "delete_fixed_event",
                "args": {"event_id": event["id"], "revision": event["revision"]},
            }]
            response = post(c, h, f"/api/agent/runs/{run['id']}/resume", {
                "approval_id": approval_id, "revision": approval["revision"], "decision": choice,
            }, f"resume-{choice}")
            assert response.status_code == 200
            assert wait_run(c, run["id"])["data"]["status"] == "done"
            assert c.get(url).status_code == (404 if choice == "approve" else 200)
