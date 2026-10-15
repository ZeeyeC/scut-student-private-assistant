# 华工大学生个人助手：第一版设计

日期：2026-10-14。修订：优先复用开源代码；用户已选择从 Web GUI 发起，通过轻量扩展打开教务标签页并自动提取。状态：供逐阶段实现的方案；尚未实现或验证产品。

## 1. 目标与假设

用户明确要求：基于 Deep Agents，从学校教务系统导入课表，通过截图导入作业，拆解任务，提供每日安排，使用跨端 Web GUI，至少支持 Windows 与 macOS。首个接入学校为华南理工大学。尽量复用开源功能、减少自写代码；课表主流程必须是 Agent 打开教务浏览器界面，用户登录并进入课表页面，扩展自动读取内容，不要求手动导出文件。

本方案默认本科生、中文界面、在线使用、个人学习安排；先支持少量独立账号，不提供团队共享。账号类型如果实际为研究生，须替换教务适配器。模型供应商尚未指定，作为配置项选择，要求文本工具调用和图片输入能力。第一版不需要原生桌面客户端。

核心闭环：真实课表 → 作业截图 → 可校对的作业 → 可编辑的步骤 → 无课表冲突的每日建议 → 完成反馈 → 重新安排。

第一版边界：一个学校；用户在 Web GUI 发起课表更新，扩展自动提取；课表和截图导入必须预览确认；每日计划按需生成。浏览器完全关闭时后台 Agent 启动浏览器、自动推送、全校通知抓取、自动提交作业、选课、成绩分析、RAG、支付和多人协作不在第一版内。

## 2. 技术方案与理由

采用 Python 3.12 + FastAPI + Pydantic + SQLAlchemy/Alembic + SQLite；前端 React + TypeScript + Vite + Tailwind CSS + TanStack Query；Deep Agents 负责对话与业务工具调用；LangGraph 持久化检查点负责会话恢复；Vitest、pytest、Playwright 负责有业务意义的验证。Node 使用 22.12+ 的 22.x 支持版本。具体依赖版本在实现阶段 01 做安装及 API 兼容探针后写入 lockfile，不凭旧教程指定 API。

这是推荐方案，不是经性能测试得出的结论。Python 便于使用 Deep Agents，SPA 便于 Windows/macOS 浏览器访问；单服务、单进程 SQLite 足以支撑个人试用。第二阶段扩大部署时再迁移 PostgreSQL，避免先引入 Redis、Celery、向量库和复杂微服务。

选择 React/Vite 而不是 SSR 框架，是因为本产品主要是登录后的交互应用，不以公开内容 SEO 为目标。

### 开源复用决策

| 能力 | 首选复用 | 自写范围 |
|---|---|---|
| Agent、工具、上下文、确认、检查点 | Deep Agents/LangChain/LangGraph 官方实现 | 学生业务工具和配置、事件适配 |
| 扩展构建和本机标签页 | WXT/TypeScript、WebExtension tabs/windows/content scripts、@webext-core/messaging | 导入会话关联、华工页面检测 |
| HTML 表格解析 | pandas.read_html + lxml | 实测的学校字段、周次/节次映射 |
| HTML 片段清理 | DOMPurify，table 标签白名单 | 选择课表容器、脱敏与完整性检查 |
| 应用账号和登录 | FastAPI Users 的 SQLAlchemy + CookieTransport + DatabaseStrategy | 首账号注册策略、CSRF/owner 注入 |
| 日历展示 | FullCalendar 标准版 React 的 TimeGrid/List | occurrence→event、学期周次切换 |
| 聊天显示与输入 | assistant-ui React primitives/custom runtime | 自有 SSE 适配、导入/确认卡片 |
| 通用组件和表单 | shadcn/ui + React Hook Form | 页面组合和作业校对字段 |
| 缓存、校验、迁移 | TanStack Query、Pydantic、SQLAlchemy、Alembic | 业务 schema、薄 service 和事务 |

FullCalendar 使用标准版，不引入 Premium 资源组件；日历显示不等于学习任务排程。assistant-ui 保留当前 FastAPI/SSE，用薄 custom runtime 接入，不因此改用 Next.js 或托管云。

FastAPI Users 官方当前处于维护模式，仍提供安全与依赖维护；阶段 01 记录选型和兼容探针。复用已有登录实现，不手写密码哈希/session 算法，也不引入独立认证服务器。

每新增模块，先记录现成库能做什么，再说明必要 glue code。不得重写已有浏览器驱动、聊天滚动/Markdown、课表网格、数据库迁移和基础鉴权。自写主要限于学校适配、学生领域、版本/幂等和排程规则。代码行数只在实现后统计，不承诺未经验证的复用比例。

## 3. 跨端与运行方式

- 开发：前端 Vite 开发服务通过 `/api` 代理连接 FastAPI；同源 cookie，浏览器无模型密钥。
- 本机模式：构建后的前端由 FastAPI 提供，一台 Windows 或 Mac 运行服务，浏览器使用。两个独立安装默认有两份数据，不声称同步。
- 同一份数据跨端：所有设备访问同一个 HTTPS 站点和后端，用同一应用账号登录。服务端数据库是唯一事实来源。先给出部署文件和操作步骤，不代替用户购买服务或发布站点。
- 主支持环境：Windows 11 上当前稳定 Chrome/Edge；macOS 14+ 上当前稳定 Chrome/Safari。响应式验证宽度 390、768、1440 CSS px。手机浏览器为增强支持；需要访问同一服务，不能把电脑 localhost 当手机服务。
- 自动学校导入使用已安装 WXT 扩展的 Windows/macOS Chrome/Edge；Safari GUI 可查询和管理已导入数据，第一版不承诺 Safari 扩展发布。每个发起导入的浏览器首次安装扩展；后续不需导出/上传课表文件。
- 云端 Agent 通过 Web GUI 的 browser_action_required 事件交给本机扩展执行；不会在云服务器上启动用户看不到的浏览器。GUI 将读取结果提交同源后端，无需桌面 daemon、本机 WebSocket 桥或开放 localhost 服务。
- Windows/macOS 兼容使用 pathlib、UTF-8、Python zoneinfo 与 tzdata；不依赖 bash 专属路径或系统 cron。提供 PowerShell 和 POSIX 启动方式。Docker 是可选部署方式，不是桌面用户必装依赖。
- 第一版不承诺离线编辑或后台提醒。若后续加 PWA，仅缓存静态资源，不缓存课表、截图、会话和 API 响应。

## 4. 系统边界

浏览器 GUI 调用 FastAPI 业务接口和 Agent 会话接口。业务服务保存课表、作业、步骤、计划和来源。Deep Agents 只能通过同一组受约束的业务服务工具访问数据，不直接写 SQL 或修改应用数据文件。

三个工作模块保持独立接口：

1. 导入：把学校数据和截图变成结构化草稿；用户校对后入库。
2. 学习任务：使用模型提出拆解和耗时估计；估计可编辑，来源事实与模型推断分开。
3. 排程：确定性程序按课程、固定事项、依赖、空闲窗口、截止日期计算安排；模型只解释结果。

Agent 内部 `write_todos` 是执行过程记录，不能代替学生 Task/TaskStep 数据。业务步骤要通过工具保存至业务数据库。是否启用规划 middleware 根据锁定版本明确配置；当前官方文档说明部分版本的任务规划需要显式启用。

默认一个主 Agent，无需求时不启用子 Agent、shell 或通用浏览器控制工具。允许 start_timetable_import 这个受限工具，让 GUI/扩展打开指定学校入口并只读提取。文件后端使用线程范围的 StateBackend/受限后端，不映射服务器根目录、上传目录或密钥目录。检查实际工具列表，不能只用 prompt 声称限制生效。

## 5. 页面与交互

桌面布局：左侧导航（今日、课表、作业、助手、设置），中间业务页面；助手可单独页面或右侧面板。窄屏使用底部导航，卡片纵向排列，课表可在周视图与当天列表间切换。

- 今日：当日课程、建议学习时间块、临近截止任务、未安排事项；支持完成、调整、重新生成。
- 课表：周次切换、课程详情、节次时间设置、例外调整；“从华工导入”打开教务标签页，显示等待登录/等待课表/读取中/待校对/失败，自动结果预览与变更差异。
- 作业：拖拽/选择截图、识别进度、原图与草稿并排核对、编辑、步骤拆解、完成状态。
- 助手：消息流和工具进度；结构化课表/作业/计划卡片、确认按钮；失败后重试。不要展示模型的内部推理链。
- 设置：应用账号、时区、学期第一周周一、周数、节次时间、可学习时间、固定事项、默认缓冲时间；模型连接由服务端配置，网页只显示可用状态。

首次使用流程：注册/登录 → 安装并检测扩展 → 设置学期锚点和节次 → Agent/按钮唤起教务标签页 → 本人登录并进入课表页 → 自动提取并确认 → 上传作业并确认 → 编辑拆解 → 生成今日计划。

模型不可用时课表查看、手工录入作业、修改步骤、完成任务、确定性排程仍可使用。

## 6. 华南理工大学课表导入

已查到官方统一认证入口 `https://sso.scut.edu.cn/cas/login`。2024 年官方院系通知曾提到 `http://xsjw2018.jw.scut.edu.cn` 和校外 VPN；该地址只作为历史线索，不能据此宣称当前入口和 API 有效。以实际学校门户和用户本人登录后的页面为准。

没有获得当前登录后样本、接口文档、学期周次和节次表；这些是阶段 03 的明确输入依赖，不填写虚构数值或接口。无需在聊天中提供密码、验证码、cookie 或完整 HAR。

第一版主流程必须自动提取：

1. Web GUI 点击“从华工导入”或对 Agent 说“导入课表”。服务端创建 BrowserImportSession，并返回/发出 browser_action_required。每个浏览器同一时刻只关联一个本次导入 session。
2. GUI 的站点 content script 通过 WXT messaging 联系扩展 background，用 browser.tabs.create/update、windows.update 打开并聚焦实测官方入口。只支持 school_id='scut'，目标 URL 来自已验证配置，模型不能提供任意 URL。
3. 用户在真实本机浏览器输入账号/验证码并进入本人课表页、选择学期；已有登录态可继续使用。程序不读取登录输入，不申请 cookies/debugger 权限，不把登录页/密码/完整 DOM 发给模型或后端。
4. 学校 content script 检测实际课表路由/容器，MutationObserver 监听动态更新；在无加载状态、表头/学期有效、数据连续稳定 1 秒后自动提取。SPA、iframe、分页/虚拟表格须实测；不完整片段不得伪装全量。
5. 只读实测课表容器。DOMPurify 保留 table/thead/tbody/tfoot/tr/th/td/span/br 的文本和 rowspan/colspan，去除脚本、表单、资源 URL 和个人标识；扩展返回原助手标签页，GUI 同源提交 capture。后端 pandas.read_html(StringIO(...)) 复用表格解析，华工 adapter 仅做字段规范化。
6. 助手自动展示预览卡片：学期、课程、周次、地点、差异；用户确认保存。抓取自动完成，用户不需下载文件、复制 JSON 或手动上传。

缺扩展时显示安装/启用入口，不以手动导出替代本需求验收。阶段 03 未真实验收前仍标“华工适配待验证”。扩展代码不能读取其他课程之外的学校资料，也不能通过模型任意导航。学校登录仍由本人操作。

协议和恢复：

- `BrowserImportSession(id, owner_id, school_id='scut', status, browser_opened_at?, expires_at, draft_id?, revision)`；状态 queued→waiting_login→waiting_timetable→extracting→preview_ready→completed，另有 failed/cancelled/expired。已有登录态可跳过 waiting_login。创建后 15 分钟过期；用户可取消/重新发起。等待登录不计入模型 job 的 120 秒；extracting 阶段 30 秒超时。
- 扩展真实创建/聚焦标签页后回传 opened 事件，GUI 通过同源 `POST /browser-imports/{id}/events` 保存进度；后端记录 browser_opened_at。waiting_timetable/extracting/failed 也经此入口更新。校验 owner、有效期、事件幂等、revision 和合法状态迁移；终态拒绝迟到事件。preview_ready 只由后端成功生成草稿设置，completed 只由确认事务设置，不能由扩展或模型自报。未收到真实 opened 回执不能宣称已开页。
- START_IMPORT 包含 session_id、protocol_version=1 和 GUI instance nonce；身份由后端应用 session 决定。扩展维护 app_tab_id、school_tab_id、app origin、session_id 关联，校验消息 sender tab/frame/origin，不能信任正文提供的身份。使用 app content script 的 window.postMessage 桥接时校验 event.source===window、event.origin 和 nonce，再调用 extension messaging；不开放任意页面触发。
- capture fragment≤1 MiB、表格≤20 个、行≤2000。仅返回脱敏表格/元数据，不含 cookie/密码/完整 URL query。后端不执行 HTML、不加载外部 URL；GUI 只显示规范化纯文本，不直接渲染原 HTML。
- MV3 background 复用 browser.storage.session、alarms 和事件监听保存关联，worker 重启不重复开标签页。学校页关闭、助手 logout/user 切换、session 过期时停止；结果 hash 幂等，页面刷新不重复保存。
- GUI 刷新后按当前用户查询 session 并恢复绑定；原助手标签页关闭时结果短暂保存在 extension session storage，用户重新打开同 origin 助手后恢复或提示，不跨账号提交。学校页不得获得应用 session token。
- 同源 POST capture 校验 owner、有效期、目标学校配置与 source_revision，同 hash 产生同一 ImportDraft。应用身份不能证明学校登录的是哪个学生，预览需本人校对。

定义规范化数据 `ScutCaptureV1`：`schema_version=1, source='scut', captured_at, semester_label, completeness: 'full'|'partial'|'unknown', courses[]`。课程包含 `source_key, name, teacher?, campus?, location?, weekday(1..7), weeks(int[]), periods(int[])`。表格片段为传输输入，规范化数据为业务输入；未知字段保留 warnings，不带学号或凭据。full 必须由实测适配器的完整性检查给出，不接受网页/模型自我声明。

扩展复用现有浏览器和本机登录态，云端 GUI/后端仍共享同一数据。当前用户负责登录/导航，程序读取固定表格，不必额外运行通用 Browser Use Agent。Playwright 用于扩展流程测试；未来要后台唤起完全关闭的浏览器时，再加入基于 Playwright 的本机连接器。

课表规范化：

- 学期第一周必须是用户校对的周一；学期周数 1..30，用户配置。单双周相对学期第一周计算。
- 周次存显式整数数组，支持 `1-8,10-16周(单)` 与不连续周次；解析不确定的条目留在预览中等待校对。
- 节次使用学校/校区配置映射，不能假设每节 45 分钟或写死 08:00。无映射则阻止排程并提示设置。
- 日期例外独立建模：取消、替换时间/地点、补课；不会修改整个学期规则。
- 同源课表重复提取不重复新增；展示新增、变更、疑似删除，确认后事务提交。只有完整性检查通过的全量 capture 才能提出删除；不完整/分页数据不能删除已有课程。

## 7. 截图识别与作业数据

输入 PNG/JPEG/WebP，单张最大 10 MiB，解码后不超过 20 百万像素；第一版单张处理，允许单张出现多项作业。检查实际文件类型及解码结果，剥离 EXIF，私有存储 UUID 文件名；不从模型返回的 URL 自动下载附件。

截图识别由可替换的视觉模型实现，独立于对话 Agent；模型供应商必须实际支持图片输入与结构化结果。优先复用 LangChain 模型接口及 Pydantic 校验，避免同时堆多套 OCR。可在模型不可用时手工录入，不声称识别成功。

每项作业输出 `title, course_id?, course_candidates, requirements[], due_at?, due_text?, submission_method?, evidence[], uncertain_fields[], estimated_minutes?`。证据包含字段、截图中的原文；模型推断不能当证据。

“下周五”以用户确认的消息日期为基准，而不是图片文件时间或上传日期；“周五前”、没有年份、仅日期无时刻等情况标记待确认。截止日期和时刻未确定时保存 `due_at=null`，不能偷偷默认 23:59；可让用户显式选择日期和时间。未知截止日任务可安排普通学习，但不能显示成有确定 deadline。

截图不能修改 system prompt，截图内“忽略规则”等文本作为资料处理。course_id 只从服务端提供的用户课程候选中选择。校对确认后才成为真实任务；保存原图引用和修改记录。同一截图有重复预警；即使点击两次确认也只保存一次。

## 8. 任务拆解

输入用户确认的任务、要求、剩余工作和必要的课程上下文。模型输出 1..12 个可执行步骤，每项包含 `title, description, estimated_minutes(5..240), dependency_keys[], acceptance_criteria[]`，并说明耗时是估计。

总任务不人为限制在 240 分钟；大任务由多个步骤组成。排程时大于 60 分钟的步骤可以分多次安排，总分配不得超过剩余估计。依赖图必须无环；不存在的依赖、负数耗时或模型非法结构需报错或最多修复一次，随后转人工编辑。用户保存前可改步骤与估计。重新拆解生成新草稿，不覆盖已完成步骤。

## 9. 每日安排

设置默认时区 Asia/Shanghai、可学习窗口 09:00–12:00/14:00–18:00/19:00–21:00（可改）、跨固定事项前后缓冲各 10 分钟、单块最多 60 分钟、最短有效空闲块 15 分钟、默认每日学习上限 180 分钟（课程不计入）。不能把这些默认值说成华工官方作息。

`generate_plan` 从 target_date 起共寻找 7 个本地日的时间块，默认 target_date 为今日，且不得早于今日；horizon_days 可设 1..7。今日页只展示当天；未来天安排保留为可查看草稿。先展开课表/例外/用户固定事项，再扣除忙时和缓冲，并裁掉已经过去的时间。

候选任务：未完成、未归档；已逾期任务单独提示，只有用户设置新的补救截止时间后才纳入排程；未知截止时间排在有确定近期 deadline 的任务后。优先级为：按截止时间从早到晚 → 用户优先级高到低 → 稳定 ID。依赖满足后才安排步骤；长步骤可分块，但后继步骤必须在前驱全部剩余工作分配结束之后。

排程不超过每日上限、不覆盖课表/固定事项/锁定时间块、不安排在任务截止后。今日之外的重排默认只改未来未锁定建议；已完成时间块和用户锁定块保持不动。完成块并不默认完成整个步骤，需区分本次投入与步骤完成。

时间不足时返回未安排分钟数及原因（截止前容量不足/依赖未满足/每日上限/无可用时间），展示超载风险；不宣称任务一定完成。刷新同一输入返回同一草稿；输入 revision 改变则产生新版本，用户确认替换旧建议；防止双端覆盖。

模型负责简短解释结构化结果，不计算最终时间；计划可在无模型情况下生成。

## 10. 数据与接口约定

实体均有 UUID、owner_id、created_at/updated_at、revision。时间瞬间存 UTC ISO 8601；本地日期和学期规则保留本地 date/time+IANA 时区；禁止 naive datetime。Course 是课程身份，CourseMeeting 是周次/节次规则，CourseException 是日期调整，CourseOccurrence 是计算结果而非独立事实表。

主要表：User、Session、StudentSettings、Semester、Course、CourseMeeting、CourseException、FixedEvent、SourceAsset、BrowserImportSession、ImportDraft、Task、TaskStep、PlanDraft、PlanBlock、Approval、AgentRun。Draft 只保存 JSON 草稿和 schema_version，confirm 才写事实表。User.study_revision 是课表、设置、固定事项、任务与步骤输入的聚合版本，修改这些事实时事务内递增；每个草稿保存 source_revision，提交前检查版本。PlanDraft/PlanBlock 自身使用 revision，双端写入也检查其版本。

HTTP 契约（所有业务接口 `/api`，鉴权且按 owner 查询）：

- `POST /auth/register|login`、`POST /auth/logout`、`GET /auth/me`；首次启动允许创建第一个账号，此后只有管理员显式开启注册，不向公开网络开放任意注册。
- `GET|PUT /settings`；`GET /calendar?from=...&to=...`，跨度最多 35 天；固定事项/课程例外 CRUD。
- `POST /browser-imports` → BrowserImportSession；`GET /browser-imports/{id}` → 状态；`POST /browser-imports/{id}/events` → 真实扩展进度；`POST /browser-imports/{id}/capture` → ImportDraft；`POST /browser-imports/{id}/cancel`；`POST /imports/{id}/confirm` → 课程变更摘要。capture 仅接收已绑定 session 的扩展结果，不是课表文件上传入口。
- `POST /imports/assignment-image` → Job；`GET /jobs/{id}` → 状态/草稿；`PATCH /imports/{id}` → 更新草稿。
- `GET|POST /tasks`、`GET|PATCH /tasks/{id}`；`POST /tasks/{id}/decomposition` → 草稿；步骤草稿确认复用 `/imports/{id}/confirm`。
- `PATCH /steps/{id}` 支持耗时编辑和完成状态；任务/步骤完成、归档、例外、固定事项修改均带 revision。
- `POST /plans/generate` → PlanDraft；`POST /plans/{id}/confirm`；`PATCH /plan-blocks/{id}` 支持锁定/实际完成。
- `POST /chat/runs` → run_id；`GET /chat/runs/{id}/events` SSE；`POST /chat/runs/{id}/decisions` 恢复确认；`GET /chat/threads/{id}` 恢复聊天记录。

写请求使用 `Idempotency-Key`，作用域 owner+操作，存 request hash；同 key 同参数返回旧结果，不同参数返回 409。修改携带 revision；旧 revision 返回 409 并提示刷新。模型草稿失败不写入课程/任务事实表。

长任务使用数据库 job 表和单进程受控 worker，状态 queued/running/succeeded/failed；单次模型请求 60 秒超时，总作业 120 秒，只对临时错误最多重试 1 次。中途关闭 UI 不取消任务。服务启动后将遗留 running 标记 interrupted/failed，并允许新请求重试，不承诺无限后台运行。

## 11. Agent 与确认机制

服务端根据会话确定 RequestContext(owner_id, timezone, now_utc)，不让模型选择 owner_id。业务工具支持 start_timetable_import/get_timetable_import_status，让 GUI/扩展打开固定学校入口并返回进度；登录仍由本人完成。其他工具仅有读取、草稿、确认和明确对象更新，不具备代填校园密码、发邮件、自动提交作业或任意文件/网络权限。开启浏览器导入有明确用户请求时直接执行，不额外确认只读开页；入库仍校对确认。

持久化 checkpointer 使用官方支持的 SQLite 实现，独立文件 `agent.sqlite3`；不能以 MemorySaver 冒充重启后恢复。thread_id/run_id 都需按 owner 验证，不以模型提供的 thread_id 直接读状态。单线程同一时刻只跑一个 Agent run；并发请求返回 409/队列提示。

只读和草稿工具直接执行；commit_import、commit_plan、set_task_status 采用 Deep Agents `interrupt_on`。GUI 展示准确参数并确认/拒绝；恢复确认时绑定 owner+run+pending tool call+payload hash，过期/已确认/版本过时不能重复提交。编辑参数后必须重新验证并展示差异。业务写入还必须验证服务端一次性 approval capability，GUI/API 不能用模型文本中的“用户已经同意”作为授权。

事件只包含公开消息、tool_started/tool_finished、browser_action_required、draft_ready、approval_required、done/error。每个事件有递增 ID，存数据库；重连从 Last-Event-ID 回放，不重新执行工具，前端去重。导入工具创建 session 后即返回，不让模型调用等待 15 分钟；GUI 查询导入状态，preview_ready 后可发起新的确认 run。拒绝后明确显示未保存。

## 12. 数据与访问保护

应用独立账号，复用 FastAPI Users 的密码/用户管理、CookieTransport 和 DatabaseStrategy 随机服务端 token；Session 表采用库的 access-token 模型而非自写算法，cookie HttpOnly、生产 Secure、SameSite=Lax；写请求补充 CSRF/同源校验。应用登录不等于学校登录。

密钥只在服务端环境变量/部署 secret，所有 VITE_ 变量均视为公开。上传原图经鉴权读取，不使用公开 `/uploads`；日志不记录完整截图、凭据或模型原始隐私内容。学校 capture 默认仅课程，不提取姓名、学号和成绩。扩展 site matches/host_permissions 只包含部署的助手 origin 和经核验的学校课表/必要 frame 域，不使用 <all_urls>；不申请 cookies/debugger/webRequest 权限，所有依赖随扩展构建，禁用远程可执行脚本。

模型调用前明示图片/作业内容将发送到配置供应商；用户可以拒绝并改用手工录入。不声称开源模型调用一定免费或本地部署一定没有外发。

提供个人数据导出与删除：删除范围包含私有截图、任务、课表、会话和检查点；保留备份的期限由部署者明确设置。SQLite 备份使用在线 backup API 或停机一致备份，不能直接拷贝活动 WAL 数据库后宣称可恢复。

## 13. 验收

1. 在 Web/Agent 发起→真实本机教务标签页打开并聚焦→本人登录/进入课表→自动抓取→预览确认，全程不导出/上传课表文件。与本人真实华工课表逐项核对课程数量、周次、节次、地点；扩展/适配版本与日期写入说明。示例/fixture 不替代真实验收。
2. 导入单双周/不连续周次课程，重复导入无新增；不完整输入不删除已有课程；学期日期映射和例外正确。
3. 准备取得使用许可且脱敏的 10 张代表性截图，逐字段核对；不要求声称固定准确率。所有不确定 deadline 必须进入校对；网络失败不保存假任务。
4. 任务拆解可编辑；环依赖和非法时长被拒绝；完成步骤重新拆解不丢失。
5. 排程无冲突、无截止后块、无过去块、无超每日上限；超载明确列出；双端旧版本不能覆盖；无模型依然可安排。
6. Windows Chrome/Edge 与 macOS Chrome/Safari 都能登录、上传、校对、拆解、看计划和完成任务；真实操作结果记录，浏览器仿真不等于操作系统实测。
7. 服务重启后数据和待确认 Agent 状态恢复；SSE 重连不重复执行；跨账号数据不能访问；部署到同一测试后端后双端能看到同一数据。
8. 自动提取在 Windows/macOS Chrome/Edge 实测；扩展未安装、登录超时、标签页关闭、MV3 worker 重启、iframe/分页和重复事件有明确状态，无跨账号提交/重复开页/静默删课。Safari GUI 与扩展导入能力分别记录。

## 14. 官方参考与核查边界

- [Deep Agents 总览](https://docs.langchain.com/oss/python/deepagents/overview)：Agent、工具和上下文能力；规划 middleware 需核对锁定版本。
- [Deep Agents 自定义](https://docs.langchain.com/oss/python/deepagents/customization)：模型、工具与后端配置。
- [人工确认](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)：interrupt_on 和 checkpointer，生产需要持久化实现。
- [流式事件](https://docs.langchain.com/oss/python/deepagents/streaming)：使用官方事件适配自有 SSE 协议。
- [LangChain 消息](https://docs.langchain.com/oss/python/langchain/messages)：图片内容块，供应商兼容性需实测。
- [Vite 安装](https://vite.dev/guide/)；[FastAPI 文件上传](https://fastapi.tiangolo.com/tutorial/request-files/)。
- [WXT](https://wxt.dev/)；[扩展消息复用](https://wxt.dev/guide/essentials/messaging)；[浏览器 content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)；[tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs)。
- [pandas.read_html](https://pandas.pydata.org/docs/reference/api/pandas.read_html.html)；[DOMPurify](https://github.com/cure53/DOMPurify)；[FullCalendar React](https://fullcalendar.io/docs/react)；[assistant-ui](https://github.com/assistant-ui/assistant-ui)；[shadcn/ui](https://github.com/shadcn-ui/ui)。
- [FastAPI Users](https://fastapi-users.github.io/fastapi-users/latest/)；[DatabaseStrategy](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/strategies/database/)。
- [华工统一认证](https://sso.scut.edu.cn/cas/login)；[官方历史教务指引](https://www2.scut.edu.cn/design/_t2289/2024/0625/c2818a557524/page.htm)；[校园 VPN](https://www.scut.edu.cn/vpn/)。未读取登录后教务页面，当前课表路由、容器、字段与自动提取效果仍需真实会话核查。
