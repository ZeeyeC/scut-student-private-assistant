"""Real local MCP protocol; frozen clock fixtures are explicitly test-only."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login


@pytest.mark.asyncio
async def test_real_official_mcp_clock_and_invalid_timezone():
    from app.time_mcp import TimeUnavailable, current_time

    before = datetime.now(ZoneInfo("Asia/Shanghai"))
    result = await current_time("Asia/Shanghai")
    after = datetime.now(ZoneInfo("Asia/Shanghai"))
    actual = datetime.fromisoformat(result["datetime"])
    assert before - timedelta(seconds=1) <= actual <= after
    assert result["timezone"] == "Asia/Shanghai"
    assert result["today"] == actual.date().isoformat()
    assert result["tomorrow"] == (actual.date() + timedelta(days=1)).isoformat()
    assert result["source"] == "mcp-server-time"
    with pytest.raises(TimeUnavailable, match="时间 MCP 查询失败"):
        await current_time("Not/A_Zone")


class RelativeDateModel(ToolModel):
    """Test-only model that exposes whether fresh date context reaches each call."""

    seen: list[str] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = str(messages[0].content)
        assert '"today": "2026-10-' in prompt
        assert '"tomorrow": "2026-10-' in prompt
        self.seen.append(prompt)
        if isinstance(messages[-1], ToolMessage):
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content=messages[-1].content))
                ]
            )
        last_user = next(m for m in reversed(messages) if isinstance(m, HumanMessage))
        name = (
            "get_current_time"
            if "日期" in str(last_user.content)
            else "list_course_occurrences"
        )
        tomorrow = "2026-10-16" if '"today": "2026-10-15"' in prompt else "2026-10-17"
        args = (
            {}
            if name == "get_current_time"
            else {"start_date": tomorrow, "end_date": tomorrow}
        )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": name,
                                "args": args,
                                "id": "date-query",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


def test_timezone_midnight_stale_history_and_restart(tmp_path, monkeypatch):
    from app import time_mcp

    clock = {"today": "2026-10-15", "tomorrow": "2026-10-16"}
    zones = []

    async def test_clock(timezone):
        zones.append(timezone)
        return {
            "source": "mcp-server-time",
            "timezone": timezone,
            "datetime": clock["today"] + "T23:59:59+09:00",
            **clock,
        }

    monkeypatch.setattr(time_mcp, "current_time", test_clock)
    model = RelativeDateModel()
    with make_client(tmp_path) as c:
        h = register_login(c)
        cookies = dict(c.cookies)
        s = c.get("/api/settings").json()
        s["data"].update(
            timezone="Asia/Tokyo",
            week1_monday="2026-08-31",
            periods={"1": {"start": "08:00:00", "end": "08:45:00"}},
        )
        assert (
            c.put(
                "/api/settings", json=s, headers={**h, "Idempotency-Key": "s"}
            ).status_code
            == 200
        )
        d = c.post(
            "/api/drafts/timetable",
            json={
                "courses": [
                    {
                        "source_key": "fri",
                        "name": "周五课程",
                        "weekday": 5,
                        "weeks": [7],
                        "periods": [1],
                    },
                    {
                        "source_key": "sat",
                        "name": "周六课程",
                        "weekday": 6,
                        "weeks": [7],
                        "periods": [1],
                    },
                ],
                "semester_label": "测试学期",
            },
            headers={**h, "Idempotency-Key": "d"},
        ).json()
        assert (
            c.post(
                f"/api/drafts/{d['id']}/confirm",
                json={"revision": d["revision"]},
                headers={**h, "Idempotency-Key": "save"},
            ).status_code
            == 200
        )
        c.app.state.agent_model_factory = lambda: model
        t = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "t"}
        ).json()
        run = c.post(
            "/api/agent/runs",
            json={
                "thread_id": t["id"],
                "message": "旧记录说今天8月30日，开学8月31日。但请查真实明天有什么课",
            },
            headers={**h, "Idempotency-Key": "r1"},
        ).json()
        assert wait_run(c, run["id"])["data"]["status"] == "done"
        events = c.get(f"/api/agent/runs/{run['id']}/events").text
        assert "周五课程" in events and "2026-10-16" in events
        assert "周六课程" not in events
    clock.update(today="2026-10-16", tomorrow="2026-10-17")
    with make_client(tmp_path) as c:
        c.cookies.update(cookies)
        c.app.state.agent_model_factory = lambda: model
        for key, message in [("r2", "明天有什么课"), ("r3", "请调用工具查当前日期")]:
            run = c.post(
                "/api/agent/runs",
                json={"thread_id": t["id"], "message": message},
                headers={**h, "Idempotency-Key": key},
            ).json()
            assert wait_run(c, run["id"])["data"]["status"] == "done"
            events = c.get(f"/api/agent/runs/{run['id']}/events").text
            if key == "r2":
                assert "周六课程" in events and "2026-10-17" in events
                assert "周五课程" not in events
            else:
                assert "get_current_time" in events and "2026-10-16" in events
    assert zones and set(zones) == {"Asia/Tokyo"}
    assert len(model.seen) >= 6


def test_clock_failure_is_visible_and_model_does_not_guess(tmp_path, monkeypatch):
    from app import time_mcp

    async def unavailable(timezone):
        raise time_mcp.TimeUnavailable(
            "本机时间 MCP 查询失败，未使用猜测日期。请重试。"
        )

    monkeypatch.setattr(time_mcp, "current_time", unavailable)
    model = RelativeDateModel()
    with make_client(tmp_path) as c:
        h = register_login(c)
        c.app.state.agent_model_factory = lambda: model
        thread = c.post(
            "/api/agent/threads", json={}, headers={**h, "Idempotency-Key": "t"}
        ).json()
        run = c.post(
            "/api/agent/runs",
            json={"thread_id": thread["id"], "message": "明天有什么课"},
            headers={**h, "Idempotency-Key": "r"},
        ).json()
        result = wait_run(c, run["id"])
        assert result["data"]["status"] == "failed"
        assert "时间 MCP 查询失败" in result["data"]["error"]
        assert model.seen == []
