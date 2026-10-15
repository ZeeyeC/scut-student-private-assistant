# 华工大学生个人助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 用户另行选择并行代理时才使用 superpowers:subagent-driven-development。Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建基于 Deep Agents 的大学生助手，完成华工课表导入、截图作业、任务拆解、每日安排和 Windows/macOS Web 交互。

**Architecture:** 单个 FastAPI 服务提供业务 API、Deep Agents 会话和 React SPA。WXT 轻量扩展在 Agent/GUI 发起后打开本机学校标签页，等待本人登录并进入课表页，自动读取并返回校对草稿；无手动导出。业务数据库保存事实，确定性程序排程。

**Tech Stack:** Python 3.12、FastAPI/FastAPI Users、Pydantic、SQLAlchemy/Alembic、SQLite、Deep Agents/LangChain/LangGraph、React/TypeScript/Vite、shadcn/ui、assistant-ui、FullCalendar 标准版、TanStack Query、WXT/@webext-core/messaging、DOMPurify、pandas/lxml、pytest/Vitest/Playwright。

**Spec:** [设计方案](../specs/2026-10-14-campus-assistant-design.md)

## Global Constraints

- Python 3.12；Node 使用 22.12+ 的 22.x 支持版本；阶段 01 兼容探针后锁定依赖，后续阶段禁止擅自换框架。
- 目标学校为华南理工大学，默认本科生；当前入口/字段/节次与学期锚点必须真实核验，不猜 API。
- Web GUI 支持 Windows 11 Chrome/Edge、macOS 14+ Chrome/Safari；自动提取扩展首版支持 Windows/macOS Chrome/Edge，Safari GUI 管理共享数据；响应式宽度 390、768、1440 CSS px。
- 用户已选择从 Web GUI 发起、安装轻量扩展；Agent 开启学校标签页，本人登录后自动提取，不要求导出/上传文件。
- 优先复用 spec 的开源决策表；不重写浏览器驱动、基础登录、日历网格、聊天通用 UI。每阶段记录复用模块及必要 glue code，不引入多个解决同一问题的框架。
- BrowserImportSession 创建后 15 分钟过期、extracting 30 秒超时；读取稳定 1 秒；fragment≤1 MiB、表格≤20、行≤2000。等待真人登录不计入模型 120 秒 job。
- 默认时区 Asia/Shanghai；时间瞬间存 UTC，课程规则保留本地日期/时间和 IANA 时区；禁止 naive datetime。
- PNG/JPEG/WebP 单张最大 10 MiB、解码后最多 20 百万像素；私有原图鉴权读取。
- 拆解 1..12 步，每步估计 5..240 分钟，无环；大于 60 分钟可分配多个计划块。
- 默认可学习窗口 09:00–12:00/14:00–18:00/19:00–21:00，缓冲各 10 分钟，块最长 60 分钟，最短空闲 15 分钟，默认每日上限 180 分钟；均可改，不是学校官方作息。
- 排程从 target_date（默认今日且不得早于今日）起共 7 个本地日，horizon_days 可设 1..7；逾期需设置补救截止日后才能安排；不确定日期需用户校对。
- 所有写入校验 owner、revision、Idempotency-Key；Agent 写入还验证服务端确认 capability。
- 模型单次 60 秒超时、作业总时限 120 秒；临时错误最多重试 1 次，非法结构最多修复 1 次。
- 无任意 shell、无学校凭据上传、无自动提交作业、无后台推送承诺；不开启未经需要的子 Agent。扩展不得用 <all_urls>、cookies/debugger/webRequest 权限或远程可执行脚本。
- 本机独立安装不等于数据同步；跨端同一数据必须连接同一 HTTPS 后端。
- 当前仓库为空目录，只有规划文档；开始实现前检查实际文件和 AGENTS.md。用户未明确要求 baoyu-translate 时不调用它。

## Review Focus

1. 单双周与不连续周次、节次缺失、学期起点错误：预览标记缺项并阻止错误排程；阶段 02。
2. 实际浏览器开页、SPA/iframe/分页、重复 capture 和 worker 重启：自动读取、不删已有课程、不重复开页/新增；阶段 03。
3. 截图多项作业、模糊相对日期、恶意指令：保留证据和未知值，确认前不写任务；阶段 04。
4. 学习容量不足、长任务依赖、双端旧版本：明确未安排量、不穿插未完成前驱、不覆盖新版；阶段 06。
5. 服务重启、SSE 重连、拒绝与重复确认：保留待确认、不重复业务写入、不谎报成功；阶段 07。

## 工作节奏

每次给编码助手总控提示词 + 一个阶段提示词，阶段结束后人工运行页面核对。任务之间串行实现，避免对接口同时改动。每阶段先读 spec 与本计划、确认已有文件，再补有意义的失败测试、实现、验证、更新进度。不把文件创建、按钮存在或 fixture 成功当真实功能验收。

核心业务测试用确定性 fixture 或 fake model，独立于真实供应商；真实模型/学校联调是另外的显式检查，并记录“执行/未执行”。当前不要求初始化 Git；如果用户已使用 Git，每个阶段通过后做一个小提交，保留未完成改动，不擅自重置。

先探测库接口，再用薄 adapter 接合已有能力。FastAPI Users 已在维护模式，需要记录版本兼容和维护状态；采用 CookieTransport+DatabaseStrategy。assistant-ui 使用 custom runtime 适配当前 SSE，而非为了使用其 Next.js 示例重构整个项目。FullCalendar 标准版只负责显示，排程规则仍在 planner。

## 目录及职责

```text
backend/
  pyproject.toml, uv.lock, alembic.ini
  app/
    main.py, config.py, db.py, errors.py
    auth/             # 应用账号、session、CSRF、owner context
    contracts/        # Pydantic 输入/输出和领域类型
    calendar/         # 学期、周次、节次、课表实例、例外、华工字段 adapter
    browser_imports/  # 导入 session、状态、自动 capture 校验
    imports/          # 来源、草稿、校对确认、幂等、job
    tasks/            # 作业、步骤、拆解和状态
    planner/          # 纯函数排程、草稿和时间块保存
    models/           # 独立模型 gateway、能力检查和超时
    agent/            # Deep Agents 工厂、工具、运行、事件和确认
    prompts/          # 运行时 system/vision/decomposition/explanation
  migrations/, tests/
frontend/
  package.json, package-lock.json
  src/
    api/              # OpenAPI 生成类型、HTTP/SSE client
    components/       # 复用 shadcn/ui、草稿校对与确认卡片
    browser-import/   # GUI 与站点 content script 的薄消息桥
    features/         # auth/settings/today/calendar/tasks/chat
    App.tsx
  e2e/
extension/
  package.json, package-lock.json, wxt.config.ts
  entrypoints/background.ts       # 标签页打开、消息绑定、worker 恢复
  entrypoints/app.content.ts      # 仅助手 origin 的 GUI 桥
  entrypoints/scut.content.ts     # 仅实测课表页的检测和只读提取
  lib/protocol.ts, lib/scut.ts, tests/, e2e/
scripts/dev.sh, scripts/dev.ps1, scripts/backup.py
deploy/Dockerfile, deploy/compose.yaml, deploy/Caddyfile
docs/decisions.md, docs/progress.md, docs/acceptance.md
```

各子目录按需要创建，不预建未用抽象；入口/routes/models/service 的拆分只在有对应职责时出现。Agent 不直接导入 ORM 写表，只调用业务 services。

## 共享类型约定

在 `backend/app/contracts/domain.py` 定义这些项目自己的类型，不把它们伪装为 Deep Agents SDK 类型：

- `RequestContext(owner_id: UUID, timezone: str, now_utc: datetime)`，由 session 注入。
- `Semester(id, name, week1_monday: date, week_count: int, timezone: str)`。
- `CourseMeeting(id, course_id, weekday: int, weeks: list[int], periods: list[int], location: str|None)`。
- `CalendarOccurrence(id, course_id, starts_at: datetime, ends_at: datetime, location: str|None)`。
- `ImportDraft(id, kind: Literal['timetable','assignment','decomposition'], payload: dict, source_revision: int, revision: int, warnings: list[str])`；payload 使用对应 Pydantic schema 校验。
- `BrowserImportSession(id, school_id, status, browser_opened_at, expires_at, draft_id, revision)` 对外返回，不返回 owner 凭据；状态定义见 spec。`BrowserImportEvent(event_id, kind: Literal['opened','waiting_timetable','extracting','failed'], revision, error_code?)` 由扩展真实回执产生，经 GUI 同源提交。`TimetableCapture(protocol_version=1, session_id, adapter_version, school_origin, captured_at, semester_label, fragments: list[str], completeness_evidence: dict)` 是 extension→GUI→backend 输入；origin/完整性由实际适配配置校验，不能仅信任正文。
- `ScutCaptureV1` 是规范化课表，含 source/semester/courses/completeness，字段见 spec 第 6 节；不作为人工导出格式。
- `AssignmentExtraction(items: list[AssignmentCandidate], warnings: list[str])`；Candidate 字段以 spec 第 7 节为准。
- `Task(id, course_id: UUID|None, title: str, requirements: list[str], due_at: datetime|None, priority: int, status: Literal['open','completed','archived'], revision: int)`；priority 1..3，3 最高。
- `StepCandidate(key: str, title: str, description: str, estimated_minutes: int, dependency_keys: list[str], acceptance_criteria: list[str])`；保存后 key 映射真实 step UUID。
- `TaskStep(id, task_id, title, estimated_minutes, spent_minutes, dependency_ids, status: Literal['open','completed'], revision)`；remaining=max(estimated-spent,0)。
- `TimeWindow(starts_at: datetime, ends_at: datetime)`；`PlanBlock(id, task_id, step_id, starts_at, ends_at, locked: bool, status: Literal['suggested','completed'], revision)`。
- `PlanInput(now_utc, timezone, horizon_days, settings, occurrences, fixed_events, steps, tasks, preserved_blocks, study_revision)`。
- `PlanResult(blocks: list[PlanBlock], unscheduled: list[UnscheduledItem], warnings: list[str], source_revision: int)`；UnscheduledItem 包含 step_id、remaining_minutes 和 reason。

领域函数可同步；网络模型、HTTP、Agent streaming 用 async。纯算法无需 RequestContext，业务 service 必须接收 RequestContext。JSON 日期 ISO 8601；TS 从 OpenAPI 生成，禁止手写另一套矛盾 schema。

---

### 阶段 01：可启动的 Web、登录、设置与持久化

**Files:** 创建 backend 的配置/数据库/鉴权/领域类型/migrations，frontend App/api/auth/settings，环境变量示例、启动脚本、`docs/decisions.md`、`docs/progress.md`。测试 `backend/tests/test_auth.py`、`test_settings.py`。

**Interfaces:** 产出 `get_context(session) -> RequestContext`、`get_settings(ctx) -> StudentSettings`、`update_settings(ctx, settings, revision) -> StudentSettings`；HTTP 实现 auth、settings 和 healthz，其他 API 暂不冒充实现。

- [ ] 1. 创建最小依赖环境并探测 Deep Agents、fake tool、SQLite checkpointer、FastAPI Users 数据库 cookie 登录、assistant-ui custom runtime、FullCalendar 和 WXT build；记录版本和开源复用决定，锁定 backend/frontend/extension 依赖。扩展业务留阶段 03。
- [ ] 2. 写失败测试 `test_session_isolated_by_owner`、`test_csrf_required_for_write`、`test_settings_persist_after_new_db_connection`、`test_stale_revision_returns_409`，断言他人资源 404、无 CSRF 写请求 403、设置重连后相同、旧版本 409。
- [ ] 3. 运行 `uv run --project backend pytest backend/tests/test_auth.py backend/tests/test_settings.py -q`，记录实现缺失导致的失败；不把安装错误当业务 red。
- [ ] 4. 用 FastAPI Users 官方路由/数据库策略实现应用账号和 session，补 CSRF、首账号策略和 ctx；用 shadcn/ui/React Hook Form 实现设置表单，复用迁移和 OpenAPI 生成。不要手写密码/session 算法。配置示例不放密钥。
- [ ] 5. 运行上述 pytest、`npm --prefix frontend run typecheck`、`npm --prefix frontend run build`；预期全部通过。
- [ ] 6. 手工重启服务，验证登录/设置；填写 progress。通过时提交（仓库已使用 Git 才执行）。

**可见成果:** 浏览器登录、配置学期；数据重启保留，尚无课程或模型伪造演示。

### 阶段 02：课表领域、周视图、手动输入和预览确认

**Files:** `calendar/{schemas,models,service,occurrences,routes}.py`、`imports/{schemas,models,service,routes}.py`、`frontend/src/features/calendar/`、`backend/tests/test_calendar.py`、`test_import_commit.py`。

**Interfaces:** 消费阶段 01 ctx/settings；产出 `parse_week_expression(text: str, week_count: int) -> list[int]`、`expand_calendar(semester, meetings, period_map, exceptions, start: date, end: date) -> list[CalendarOccurrence]`、`create_import_draft(ctx, kind, payload, source_id=None) -> ImportDraft`、`commit_import(ctx, draft_id, revision, idempotency_key) -> CommitSummary`。事务内更新 study_revision。

- [ ] 1. 写失败测试：`parse_week_expression('1-8,10-16周(单)',16)==[1,3,5,7,11,13,15]`；周一锚点 2026-09-07、只第 1/3 周周一上课，在查询 9 月整月时仅 09-07/09-21；取消例外后只剩 09-21。
- [ ] 2. 写缺节次映射测试，断言明确 ValidationError，不默认 08:00；确认同一草稿两次返回同一摘要；改学期设置后旧草稿返回 409。
- [ ] 3. 运行 `uv run --project backend pytest backend/tests/test_calendar.py backend/tests/test_import_commit.py -q`，确认 red。
- [ ] 4. 实现上述函数、设置/固定事项/例外、课表读取和预览确认；FullCalendar 标准版显示周视图/当天列表，只写事件映射。先使用 ScutCaptureV1 fixture 验证领域，不创建面向用户的课表文件上传主流程，也不声明华工适配完成。
- [ ] 5. 运行测试及前端 typecheck/build；检查 390px 当天列表可用、1440px 周视图可用。
- [ ] 6. 更新 progress 和可选提交。

**可见成果:** 人工录入或测试 JSON 能显示真实日期课表，导入前可改周次/节次。

### 阶段 03：开源扩展唤起浏览器、自动读取华工课表

**Files:** `extension/wxt.config.ts`、`extension/entrypoints/{background,app.content,scut.content}.ts`、`extension/lib/{protocol,scut}.ts`、`extension/tests/`、`extension/e2e/import.spec.ts`；`backend/app/browser_imports/{schemas,models,service,routes}.py`、`backend/app/calendar/scut.py`、`backend/tests/fixtures/scut/`、`test_scut_import.py`、`test_browser_import.py`；`frontend/src/browser-import/bridge.ts`、`frontend/src/features/calendar/ImportTimetable.tsx`、`docs/scut-import.md`。

**Interfaces:** `start_browser_import(ctx, school_id: Literal['scut']) -> BrowserImportSession`、`get_browser_import(ctx, id) -> BrowserImportSession`、`record_browser_import_event(ctx, session_id, event: BrowserImportEvent, idempotency_key) -> BrowserImportSession`、`capture_browser_import(ctx, session_id, capture: TimetableCapture, idempotency_key) -> ImportDraft`、`cancel_browser_import(ctx, id) -> BrowserImportSession`；`parse_scut_capture(capture: TimetableCapture) -> ScutCaptureV1`。扩展 `startImport(session_id, appNonce)` 打开学校标签页，`detectTimetable(document)` 检测稳定课表，`captureTimetable(document) -> TimetableCapture` 只读片段。完整性由实测 adapter 判断，复用 create_import_draft/commit_import。

- [ ] 1. 使用 WXT 官方 TypeScript 模板，@webext-core/messaging 管理 extension 内消息；复用 tabs/windows、storage.session、alarms，DOMPurify 清理片段，pandas.read_html/lxml 解析表格。记录各库承担的功能，自写只做绑定/校验和学校映射。
- [ ] 2. 在本人会话核验当前学校入口、身份、实际课表路由/iframe/分页、字段、周次和校区节次；创建脱敏 DOM fixture。缺真实输入标 external_input_required，扩展基础通信/本地测试照常实现，真实学校适配不标完成。
- [ ] 3. 写失败测试：课表字段映射正确；不完整 capture 不删课程；重复 hash/事件仅一个草稿；旧/过期/他人 session 拒绝；1 MiB/20 表/2000 行限制；登录表单和资源 URL 不进入 payload。真实 opened 事件才设置 browser_opened_at；已有登录态可跳过等待登录；终态/乱序事件拒绝；capture 成功/确认事务分别设置 preview_ready/completed，客户端不能自报完成。
- [ ] 4. 写扩展测试：重复 START_IMPORT 只开一个 tab；sender origin/tab/frame 不符拒绝；仅有登录页不提取；稳定课表自动抓取；worker 重启/GUI 刷新恢复；标签页关闭/用户 logout 明确停止；无 <all_urls>/cookies/debugger/webRequest 权限。
- [ ] 5. 运行 `uv run --project backend pytest backend/tests/test_scut_import.py backend/tests/test_browser_import.py -q` 与 `npm --prefix extension run test`，确认真实缺失行为的 red。
- [ ] 6. 实现 spec 第 6 节状态机及 app↔extension↔school 消息；按钮发起即可开页，不等阶段 07 才可使用。等待本人登录和进入课表后自动读取；GUI 同源上传片段、pandas 解析、生成草稿并聚焦预览。不得要求用户导出/上传课表。
- [ ] 7. 运行上述测试、`npm --prefix extension run typecheck`、`npm --prefix extension run build`、`npm --prefix extension run test:e2e`。Playwright 的扩展 persistent context 使用独立临时 profile，不能自动化默认 Chrome 用户目录。用本地仿真登录→SPA/iframe 课表站点覆盖浏览器流程。
- [ ] 8. 在本人真实华工页面实测按钮→开页→登录/课表→自动提取→校对确认；重复刷新无新增。Windows/macOS Chrome/Edge 分别记录结果。本地 fixture 不能替代此验收。
- [ ] 9. docs/scut-import.md 记录实测入口、域/frame 权限、adapter 版本/日期、完整性判据、安装方式、限制；更新 progress，提交。

**可见成果:** 网页发起唤起真实本机教务标签页，登录/进入课表后自动提取，不导出文件。Agent 在阶段 07 复用同一 start_browser_import service。

### 阶段 04：截图识别、原图校对与作业保存

**Files:** `models/gateway.py`、`imports/{assets,worker,vision}.py`、`tasks/{models,schemas,service,routes}.py`、`prompts/assignment_extraction.md`、`frontend/src/features/tasks/ImportAssignment.tsx`、`frontend/src/components/DraftReview.tsx`。测试 `test_assignment_import.py`、`test_asset_access.py`。

**Interfaces:** `ModelGateway.extract_assignments(image_bytes, mime_type, courses, reference_time: datetime|None) -> AssignmentExtraction`；`enqueue_assignment_import(ctx, asset_id) -> Job`；`get_job(ctx, job_id) -> Job`；`list_tasks(ctx, filters) -> list[Task]`；草稿提交复用 commit_import。

- [ ] 1. 写失败测试：含两项作业时输出两条候选；“下周五”无消息日期时 due_at is None 且 uncertain_fields 含 due_at；截图指令不进入 system；模型选择非候选课程时拒绝。
- [ ] 2. 写上传验证测试：伪 PNG、超 10 MiB、超 20 百万像素拒绝；其他用户无法读取原图；重试确认不重复建任务；模型超时返回失败 job 且 Task 数量为 0。
- [ ] 3. 运行 `uv run --project backend pytest backend/tests/test_assignment_import.py backend/tests/test_asset_access.py -q`，确认 red。
- [ ] 4. 实现私有图片存储、模型 gateway、受控 worker、Pydantic 结构校验、图片与字段并排校对、日期基准输入、任务列表/详情/手工新增。网络模型失败时允许手工录入。
- [ ] 5. 运行测试和前端检查；用已配置视觉模型做一张脱敏图 smoke，记录调用模型与实际结果；没有密钥时写“真实识别未验证”，不能 fake 通过。
- [ ] 6. 更新 progress，提交。

**可见成果:** 上传截图→处理→可编辑候选→确认后真实作业；完整数据来自同一后端。

### 阶段 05：可编辑任务拆解与完成反馈

**Files:** `tasks/{decomposition,steps}.py`、`prompts/task_decomposition.md`、`frontend/src/features/tasks/TaskDetail.tsx`、`backend/tests/test_decomposition.py`。

**Interfaces:** 消费 Task / gateway；`ModelGateway.decompose_task(task: Task, completed_steps: list[TaskStep]) -> list[StepCandidate]`；`create_decomposition_draft(ctx, task_id) -> ImportDraft`；`update_step(ctx, step_id, changes, revision) -> TaskStep`。保存草稿时 key 转 UUID，不覆盖已完成步骤。

- [ ] 1. 写失败测试：1..12 步、每步 5..240 分钟；A→B→A 依赖拒绝；未知依赖拒绝；超过 240 分钟的整体任务可以分多步；重新拆解后已完成步骤仍存在。
- [ ] 2. 写耗时/完成反馈测试：更新 spent_minutes 后剩余正确，投入时间不自动标记完成整个步骤；旧 revision 409。
- [ ] 3. 运行 `uv run --project backend pytest backend/tests/test_decomposition.py -q`，确认 red。
- [ ] 4. 实现结构化拆解、估计说明、依赖校验、编辑确认、状态/耗时 API 和详情页面。
- [ ] 5. 运行测试与前端检查，使用一项实际作业验证步骤是否具体可执行；保留用户编辑结果。
- [ ] 6. 更新 progress，提交。

**可见成果:** 大作业拆成步骤，可改耗时、记录投入和标记完成。

### 阶段 06：确定性每日/七日排程

**Files:** `planner/{engine,models,service,routes}.py`、`prompts/plan_explanation.md`、`frontend/src/features/today/TodayPage.tsx`、`backend/tests/test_planner.py`、`test_plan_revision.py`。

**Interfaces:** `build_plan(plan_input: PlanInput) -> PlanResult` 为纯函数；`generate_plan(ctx, target_date: date, horizon_days: int=7) -> PlanDraft`；`commit_plan(ctx, draft_id, revision, idempotency_key) -> PlanSummary`；`update_plan_block(ctx, block_id, changes, revision) -> PlanBlock`。

- [ ] 1. 写失败测试：课程 10:00–11:00 加各 10 分钟缓冲，任何建议块不得与 09:50–11:10 相交；固定 now=10:30，开始不得早于 now；每日总量≤180 分钟。
- [ ] 2. 测试长步骤 120 分钟分成两块，其后依赖步骤只能在全部 120 分钟结束后开始；截止前不足时返回准确 remaining_minutes；过期未补救任务不排；未知截止任务仍可排普通学习。
- [ ] 3. 测试输入一致输出稳定、锁定/已完成块保留、旧 source_revision 或 plan revision 返回 409；设置时区 America/New_York 并使用 tzdata，DST 日不产生 naive/倒序时间块。
- [ ] 4. 运行 `uv run --project backend pytest backend/tests/test_planner.py backend/tests/test_plan_revision.py -q`，确认 red。
- [ ] 5. 实现忙时合并、空闲扣除、稳定排序、依赖解锁、跨日分块、容量/超载说明和计划草稿确认；今日页支持完成、锁定和重新生成。计划解释可调用模型，失败保留结构化结果。
- [ ] 6. 运行测试和前端检查；无模型配置下验证实际课表+作业仍能生成无冲突计划；更新 progress，提交。

**可见成果:** 可执行且可调整的今日计划，容量不足明确说明，不靠模型猜时间。

### 阶段 07：真正的 Deep Agents 对话与持久化确认

**Files:** `agent/{factory,tools,runs,events,approvals,routes}.py`、`prompts/student_assistant.md`、`frontend/src/features/chat/`、`frontend/src/components/ApprovalCard.tsx`。测试 `test_agent_tools.py`、`test_agent_recovery.py`、`test_sse_replay.py`。

**Interfaces:** `create_student_agent(model, checkpointer, business_services)` 封装锁定版 create_deep_agent；`start_run(ctx, thread_id, message, asset_ids) -> AgentRun`；`list_events(ctx, run_id, after_event_id) -> list[PublicEvent]`；`resume_run(ctx, run_id, decision: Decision, approval_id) -> AgentRun`。

**工具契约:** `get_student_context()`、`start_timetable_import(school_id='scut')`、`get_timetable_import_status(session_id)`、`list_course_occurrences(start_date,end_date)`、`list_tasks(status)`、`create_assignment_draft(title,requirements,due_at,course_id)`、`propose_decomposition(task_id)`、`propose_daily_plan(target_date)`、`commit_import(draft_id,revision)`、`commit_plan(draft_id,revision)`、`set_task_status(task_id,status,revision)`。ctx/幂等键/capability 都由服务端注入；start_timetable_import 调阶段 03 service，返回 session/browser_action_required，不阻塞等真人登录。Agent 不自行操纵登录页；commit 工具不跳过业务验证。

- [ ] 1. 使用 fake tool-calling model 写失败测试：查询调用真实 service；“导入华工课表”创建实际 session/browser_action_required；只允许 scut，无任意 URL；owner_id 不受模型控制；不含 shell/execute/任意读取；write_todos 不新增学生 Task。
- [ ] 2. 写恢复测试：确认前事实不变；关闭 checkpointer 并重建 agent，仍有 pending confirmation；reject 后无写入；同 approval 确认两次只有一次写；输入 revision 改变后拒绝旧确认。
- [ ] 3. 写 SSE 测试：事件重连只回放 after_event_id 后的事件，不重跑 tool；另一用户读 run/thread 为 404；同线程并发 run 返回 409。
- [ ] 4. 运行 `uv run --project backend pytest backend/tests/test_agent_tools.py backend/tests/test_agent_recovery.py backend/tests/test_sse_replay.py -q`，确认 red。
- [ ] 5. 实现受限工具、SQLite 持久化、interrupt_on、确认 capability、公开事件和 browser_action_required 投影；用 assistant-ui primitives/custom runtime 复用消息、输入、滚动和 Markdown，只写 SSE adapter、导入/确认卡片。不复制一个不兼容自有传输的整套 Next.js 模板，不发送 reasoning。
- [ ] 6. 运行测试；真实模型验证“导入华工课表”（必须开真实 tab 并跟进状态）、“明天有什么课”“拆解报告”“安排今天”；缺模型标未验证。
- [ ] 7. 更新 progress，提交。

**可见成果:** Deep Agents 唤起本机教务标签页、跟进自动提取，查询/提出草稿/确认/提交；聊天刷新与重启可恢复。

### 阶段 08：Web 全流程整合与响应式质量

**Files:** `frontend/src/{App,components,features}/` 所需修改、`frontend/e2e/student-flow.spec.ts`、`frontend/e2e/recovery.spec.ts`、`frontend/src/api/client.ts`。

**Interfaces:** 仅消费现有 OpenAPI 和 SSE PublicEvent；新增 API 必须先修改服务端 schema 并重新生成 TS。

- [ ] 1. 写 Playwright 失败流程：注册/登录→设置→扩展开本地模拟教务 tab→模拟本人登录/进入课表→自动提取 fixture→校对→截图 fake gateway→拆解→计划→完成。本地 extension+GUI 端到端不替代真实学校/模型联调。
- [ ] 2. 写第二账号越权、空态、解析失败、离线请求、409 冲突、重复点击确认和聊天断线恢复的页面断言；在 390/768/1440px 都能操作主要按钮和读到截止日期。
- [ ] 3. 运行 `npm --prefix frontend run test:e2e`，记录具体 red。
- [ ] 4. 复用 shadcn/ui、React Hook Form、assistant-ui 与 FullCalendar 补齐业务组合/反馈；扩展检测、安装提示、等待登录/课表、取消和超时状态可操作。作业截图仍可文件选择；课表主流程不能出现导出文件要求。
- [ ] 5. 运行前端 typecheck/test/build/test:e2e 与扩展 typecheck/test/build/test:e2e；Chromium 验证扩展，WebKit 只验 GUI，不宣称已验证 Safari 扩展。
- [ ] 6. 用真实浏览器走一次完整流程，记录未覆盖环境；更新 progress，提交。

**可见成果:** 完整 GUI 闭环，用户无需看 API 或模型原始 JSON。

### 阶段 09：同一后端部署、跨端数据与备份

**Files:** `deploy/{Dockerfile,compose.yaml,Caddyfile}`、`scripts/{dev.sh,dev.ps1,backup.py}`、`backend/app/main.py` 静态路由、`docs/run-and-deploy.md`、`backend/tests/test_backup.py`、`test_data_export_delete.py`。

**Interfaces:** 构建 frontend dist 由 API 同源提供；环境变量 DATABASE_URL、AGENT_DB_PATH、UPLOAD_DIR、MODEL_PROVIDER、TEXT_MODEL、VISION_MODEL、MODEL_API_KEY、PUBLIC_ORIGIN；静态 SPA fallback 不吞 /api 错误。

- [ ] 1. 写失败测试：备份还原后课程/任务/计划/会话一致；删除本人数据后图片和会话检查点不可取回；另一账号数据仍在；/api/not-found 返回 JSON 404 而非 SPA HTML。
- [ ] 2. 运行 `uv run --project backend pytest backend/tests/test_backup.py backend/tests/test_data_export_delete.py -q`，确认 red。
- [ ] 3. 实现一致备份/恢复/删除、同源静态服务、生产 cookie/CSRF、HTTPS 模板和持久化卷；WXT 构建匹配该 PUBLIC_ORIGIN 的 Chrome/Edge 扩展包和首次安装说明，开发/生产域权限分开。服务器密钥不进前端/扩展，不未经授权发布扩展商店。
- [ ] 4. 运行测试、前端 build；验证 `pwsh scripts/dev.ps1` 和 `sh scripts/dev.sh` 所需环境说明。只在实际能运行的系统记录成功，不能用文件存在代替 Win/Mac 实测。
- [ ] 5. 同一受控后端验证 Win/Mac 同账号共享数据；云端 Agent 发出的指令必须打开发起 GUI 所在机器的学校 tab，而非云服务器浏览器。验证扩展生产 origin/权限；备份→停止→恢复核对。计划阶段不发布。
- [ ] 6. 更新 progress，提交。

**可见成果:** 可部署为一个跨端站点；本机模式和共享服务模式说明清楚。

### 阶段 10：真实验收与第一版发布检查

**Files:** `docs/acceptance.md`、`docs/progress.md`，仅修复验收发现的相关代码及回归测试。

**Interfaces:** 不增加新功能，验证 spec 第 13 节的全部结果。

- [ ] 1. 创建验收矩阵：真实华工自动提取、10 张截图、拆解/排程、模型失败、Agent/扩展恢复、越权、两系统 GUI/扩展浏览器。分别记录输入、预期、实际与状态，不混淆 Safari GUI 和 Chromium 扩展。
- [ ] 2. 真实“Agent 请求→扩展开页→本人登录/进入课表→自动捕获→确认”全程无课表文件导出/上传，逐字段核对；截图逐字段校对，不凭少量示例宣称准确率。
- [ ] 3. Win/macOS Chrome/Edge 实测自动提取和完整流程；macOS Safari 实测 GUI/共享数据，不承诺扩展导入；缺设备标未执行。
- [ ] 4. 修复失败补回归测试，再运行 backend pytest、frontend typecheck/test/build/test:e2e、extension typecheck/test/build/test:e2e。
- [ ] 5. 标记哪些验收已通过，剩余限制明确列出；真实华工导入、截图真模型或系统实测缺失时，不宣称第一版全部完成。
- [ ] 6. 在用户要求发布时再执行部署；报告当前完成阶段、结果和已知限制。

**可见成果:** 有证据的第一版验收报告和可演示工作流。

## 分阶段耗时的使用方式

不以固定天数保证交付。阶段 03 受学校当前页面与本人会话影响最大；阶段 07 是状态恢复/确认的主要复杂点。先在阶段 01 测出 SDK 和模型兼容性，再依据实际结果估算。学校联调缺输入时可继续阶段 04–09，最终验收必须回到阶段 03，不能把手工输入当学校适配完成。

## 配套提示词

见 [Vibe coding 总控、阶段提示词和运行时提示词](../../prompts/campus-assistant-vibe-coding.md)。首次粘贴总控 + 阶段 01；后续仅执行一个阶段，保留失败证据和 progress，避免在长对话里遗失决策。

## 本次规划自检

覆盖检查：课表/华工（02–03）、截图（04）、拆解（05）、每日安排（06）、Deep Agents（07）、GUI（每个阶段与 08）、跨端共享数据（09–10）。Review Focus 五类均有拥有实现的阶段和对应测试。SDK 细节标为兼容探针而不是猜测；学校登录后的字段与完整性是实测依赖。当前没有产品测试结果，文档中的命令是未来执行步骤。
