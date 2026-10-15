# 本机日期与时间 MCP

本项目直接使用 MCP 官方参考实现 [mcp-server-time](https://github.com/modelcontextprotocol/servers/tree/main/src/time)（MIT），通过 [LangChain MCP Adapters](https://docs.langchain.com/oss/python/langchain/mcp) 接入 Deep Agents。没有重写获取当前时间的实现，也无需配置第三方时间 API、另装 Python/Node 或启动常驻 daemon。

锁定版本：mcp-server-time 2026.10.10、langchain-mcp-adapters 0.3.2、MCP Python SDK 1.30.0。SDK 限定 >=1.29,<2，完整传递依赖在 backend/uv.lock。

- 每次模型调用前，通过 stdio MCP 查询当前日期，按学生“设置”中的 IANA 时区计算 today/yesterday/tomorrow，默认 Asia/Shanghai。
- Agent 新增只读工具 get_current_time，无模型可指定的 owner、命令或服务器 URL。只接入固定本机官方时间服务器；官方 convert_time 未加入业务工具白名单。
- 涉及“明天”的课程查询先核对日期，再调用 list_course_occurrences。开学周一仅用于计算教学周，旧聊天日期不作为今天。
- 时间查询失败时明确提示“本机时间 MCP 查询失败”，不回退到猜测日期。每次查询独立连接；子进程退出由官方 SDK 管理，不留下常驻服务。
- 时间来自操作系统时钟，而非联网授时；用户修改时区后下一轮生效。截图内“明天交”等相对截止日期仍依据用户校对的消息日期，不因新增时钟而自动改写。

桌面包内携带原版开源服务器。冻结程序使用专用 --time-mcp 子进程入口；源码环境使用项目 Python 执行 python -m mcp_server_time。只写必要的连接、时区注入与结果校验代码。无需修改 .env。

## 重跑

从项目根目录运行：

```sh
uv run --project backend --no-sync pytest backend/tests -q
uv run --project backend --no-sync python scripts/verify-time.py
uv run --project backend --no-sync python scripts/verify-desktop.py 'dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion'
```

PowerShell 用相同 uv 命令，将最后的可执行文件路径换为 Windows 原生构建的 dist/desktop/CampusCompanion/CampusCompanion.exe。桌面自检需要5173端口空闲，不会自动停止现有服务。

verify-time.py 会调用已配置的真实模型并产生 API 费用，只发送虚构课表和明确标注的旧日期测试记录，使用临时数据库，不修改个人资料。它通过公开 LangGraph aget_state 核对实际工具参数。跨午夜/服务重启回归使用明确测试时钟和测试模型；真实时钟测试另外走官方 MCP 协议。

2026-10-15 已实测 macOS arm64 桌面内置 MCP，以及真实 OpenRouter openai/gpt-6-luna：“明天有什么课？”先调用日期工具，再以2026-10-16作为起止日期查询并返回虚构课程。Windows原生运行仍需目标设备验收。
