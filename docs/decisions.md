# 依赖与实现决策

Python 3.12.11；Node 22.22.0（执行时使用临时安装，用户环境要求 22.12+ 的 22.x）。版本来源为实际安装，完整传递依赖见 backend/uv.lock、两个 package-lock.json。

核心版本：Deep Agents 0.7.25、LangChain 1.4.5、LangGraph 1.2.15、checkpoint-sqlite 3.1.2；FastAPI 0.143.1、FastAPI Users 15.0.5、SQLAlchemy 2.0.54、Alembic 1.20.0、Pydantic 2.14.1；React 19.3.0、Vite 8.3.4、assistant-ui 0.15.28、FullCalendar 6.1.20、WXT 0.21.4。

- [FastAPI Users 官方](https://fastapi-users.github.io/fastapi-users/latest/)处于维护模式，继续安全及依赖维护。实际注册/DatabaseStrategy/CookieTransport 登录与持久化已探测，复用密码哈希和 token 存储。CSRF、同源和注册开关是必要连接代码。
- [Deep Agents API](https://reference.langchain.com/python/deepagents/graph/create_deep_agent)：实际源码探测默认有 Filesystem/SubAgent middleware。按同名 middleware 替换为空能力，断言最终工具清单。SQLite 探针确认 interrupt/resume 有效。没有自行实现 Agent 运行循环。
- [FullCalendar v6](https://legacy.fullcalendar.io/v6/upgrading-from-v5)：latest 混装 React v7 和插件 v6 导致 typecheck 失败，统一使用标准版 6.1.20。不重写日历网格。
- [assistant-ui custom runtime](https://www.assistant-ui.com/docs/runtimes/custom/overview)：保留自有 FastAPI SSE，采用 external store runtime。不得按 LangGraph Server 协议连接。
- [WXT](https://wxt.dev/guide/essentials/entrypoints.html)：构建、浏览器 API、消息由 WXT/@webext-core/messaging 复用。学校入口/DOM 使用已实测配置；没有配置时不猜选择器、不申请历史域权限。
- DOMPurify 清理白名单表格；服务端 lxml 验证片段边界，pandas.read_html 解析，学校字段映射为自写部分。
- SQLAlchemy Resource 表保存经过领域 Pydantic 校验的版本化聚合；Receipt 表保存幂等回执。复用 Alembic 迁移，SQLite BEGIN IMMEDIATE 保证短业务写入与回执原子性。业务 revision 在 settings 聚合统一推进，避免双端旧草稿覆盖。

- FullCalendar 命名时区复用官方 @fullcalendar/luxon3 6.1.20 与 Luxon 3.7.2（实际 package 源码的 NamedTimeZoneImpl、peerDependencies 与前端构建探针验证），同时显式固定间接 daygrid 6.1.20 避免 npm 浮动到6.1.21。
- 截止时间更新后，对区间外保留建议也重验；旧建议的耗时不是不可变事实。草稿准确展示待移除建议并经确认事务更新，锁定块仍需本人先解锁。

A方案新增：PyInstaller6.22.3 + hooks-contrib2026.8原生onedir，复用Python运行时打包；Radix Dialog1.3.1提供模态焦点管理。桌面强制local、127.0.0.1:5173；FastAPI静态资源同源供GUI，无日常Node/Vite。默认Config.local，compose模板显式shared；FastAPI Users会话机制保留。local_profile通过Alembic0002绑定旧资料，不合并owner。Windows进程存活检查使用无副作用OpenProcess/WaitForSingleObject，POSIX才用signal0。
