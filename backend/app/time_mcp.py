"""Fixed, local-only connection to the unmodified official Time MCP server."""

import asyncio
import json
import sys
from datetime import datetime, timedelta

from langchain_mcp_adapters.client import MultiServerMCPClient


class TimeUnavailable(RuntimeError):
    pass


def server_command():
    if getattr(sys, "frozen", False):
        return sys.executable, ["--time-mcp"]
    return sys.executable, ["-m", "mcp_server_time"]


async def current_time(timezone: str) -> dict:
    try:
        return await _query(timezone)
    except Exception as exc:
        raise TimeUnavailable(
            "本机时间 MCP 查询失败，未使用猜测日期。请重试或重启助手。"
        ) from exc


async def _query(timezone: str) -> dict:
    command, args = server_command()
    client = MultiServerMCPClient(
        {"time": {"command": command, "args": args, "transport": "stdio"}},
        handle_tool_errors=False,
    )
    async with asyncio.timeout(10):
        tools = await client.get_tools(server_name="time")
        clock = next(t for t in tools if t.name == "get_current_time")
        blocks = await clock.ainvoke({"timezone": timezone})
    result = json.loads(next(b["text"] for b in blocks if b["type"] == "text"))
    timestamp = datetime.fromisoformat(result["datetime"])
    if result["timezone"] != timezone or timestamp.utcoffset() is None:
        raise ValueError("时间 MCP 返回的时区或日期无效")
    today = timestamp.date()
    return {
        **result,
        "source": "mcp-server-time",
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
    }
