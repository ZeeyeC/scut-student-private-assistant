# 实施进度

2026-10-14，实际执行中。原目录仅含三份规划文档，无应用代码、无 Git；保留原文档，不初始化 Git。

## 执行约定与接口检查

按原十阶段串行实施，每阶段先测试再实现，校验结果后继续。
01 ctx/settings → 02 草稿/课程 → 03 导入会话；04 作业复用 02 确认事务；05 步骤 → 06 排程；07 业务工具复用 01–06 service；08 GUI 仅消费 API；09 同源与备份；10 真实验收。接口无已知冲突。

Ruling: 当前没有 Git，依用户计划直接在原目录工作，以本文作执行 ledger，不运行依赖 Git 的 worktree/提交脚本。风险：没有提交历史，保留原文件并使用一致备份。

## 阶段状态（2026-10-15 更新）

1. 本地实现/验证通过：Python 3.12、FastAPI Users cookie 登录、CSRF、设置、Alembic、SQLite；实际 SDK 兼容探针与 lockfile 完成。
2. 本地实现/验证通过：课程领域、周次/节次、FullCalendar、变更与可编辑预览、确认事务。
3. 实现完成、本地模拟验收通过；本人登录后的真实华工 DOM 已实测并建立专用适配。真实 Chrome/Edge 学校扩展安装运行 external_input_required。
4. 实现完成，真实 API 上传/多作业草稿/校对/确认测试通过；OpenRouter Luna 真实图片输入与多作业结构化输出协议已通过，真实中文截图准确率 external_input_required。
5. 本地实现/验证通过：持久任务、可编辑拆解/DAG/实际投入/完成状态、并发版本拒绝；真实 Luna 中文虚构阅读报告拆解已通过结构化字段与依赖 DAG 验证，仍需实际学生作业质量验收。
6. 本地实现/验证通过：确定性排程、未安排原因、锁定冲突、过期补救与旧建议重验。
7. 本地实现/验证通过：真实 Deep Agents + 11 业务工具 + SQLite checkpoint/HITL/SSE；OpenRouter Luna 真实业务查询、待审批、独立进程重启恢复、批准与幂等已通过（虚构数据）。
8. 响应式真实 API GUI 本地联调通过（390/768/1440px）；图片上传/多作业校对/未批准不写/批准后保存/刷新持久化 GUI 回归通过。
9. 同源服务、Windows/macOS 启动脚本、Docker/Caddy 文件与停机双库/图片备份恢复已提供；真实暂停 Agent 备份恢复测试通过。Docker/PowerShell 本机无运行时，未实机验证；同一后端双设备待实测。
10. external_input_required：真实中文作业截图样本；本人校对节次钟点；Windows/macOS Chrome/Edge 实际扩展完整流程、Safari Web、同后端双设备验证。真实 OpenRouter 模型协议已验收；2026–2027 第1学期的第1周周一已由本人确认是2026-08-31。

## 外部条件与边界

- 已实际打开本人提供的华工主入口，并在本人登录后的独立个人课表页测得 DOM，无 iframe；2026–2027 第 1 学期，23 条蓝色已选课程安排，含分段单双周及第21–22周。未保存姓名、学号或整页；详见 docs/scut-import.md。
- 课表未显示节次钟点，不猜测；本人已确认第1周周一为8月31日，结合实测2026–2027第1学期记录为2026-08-31（星期一）。生产助手尚未创建用户账号，日期需在该用户“设置”中保存；此记录不冒充数据库已保存。
- 根目录 .env 已由本人配置 OpenRouter，TEXT_MODEL/VISION_MODEL=openai/gpt-6-luna，MODEL_BASE_URL=https://openrouter.ai/api/v1；密钥不输出、不进入前端或版本库。verify-models.py 与 verify-agent.py 已实际调用真实供应商通过；仅使用合成图片和虚构学生数据。
- 模拟学校与 FakeVision/ToolModel 仅在 tests；浏览器模拟通过不表述为真实学校、模型或 Windows 已验证。
- 没有公开部署、发布商店、操作学校选课/提交或索取学校密码/cookie。

## 阶段 01–02 实际验证

- Python 3.12.11 已安装 runtime；uv sync 成功；三个 lockfile 已生成，Node 22.22.0 可用。
- backend/.venv/bin/python -m pytest backend/tests -q：阶段 01 的 3 项先 RED 后 GREEN；阶段 02 新增 3 项先 RED 后 GREEN；阶段 03 后端累计 9 passed。
- 登录、CSRF、账号设置隔离、持久化、旧 revision、幂等键不同载荷均有实际测试。
- Deep Agents SQLite probe：工具列表仅 ping，interrupt=True，approve 后 pong。只是 SDK fake-model 探针，不是真实模型验收。
- frontend build：FullCalendar 版本统一后通过。WXT 空扩展 typecheck/build 通过；阶段 03 实际扩展校验正在进行。
- 尚未完成阶段 01 GUI 重启/浏览器操作和 assistant-ui runtime 编译探针，阶段 08 补验；不声称整阶段真实验收完成。
- 阶段 03 后端使用明确标注的 fixture.scut.edu.cn 测试适配配置：状态/真实 opened 回执语义、重放、capture、确认、终态拒绝通过；生产配置未提供时返回 external_input_required。

## 阶段 03–06 进度

- 扩展提取测试 2 passed（先 RED）；真实域权限未配置时只有助手精确 origin，不启用历史学校入口。WXT build 产出 MV3 包。尚缺 sender/worker 浏览器端到端测试，实际学校验收 external_input_required。
- 阶段 04：私有 PNG 规范化、尺寸/类型检查、模型图片输入与结构化接口、多作业校对、确认入库、后台 job 失败；3 个新增测试先 RED 后 GREEN；真模型未调用。
- 阶段 05：无环依赖、未知依赖、整体大于 240 分钟、投入不自动完成、旧版本、重新拆解保留已完成步骤；2 个新增测试先 RED 后 GREEN。
- 阶段 06：课程缓冲、当前时间、每日上限、120 分钟步骤拆块及后继解锁、准确未安排分钟、过期补救、未知截止、锁定块、DST；3 个新增测试先 RED 后 GREEN。累计后端 17 passed。
- 今日、课表、作业、设置已接真实后端。所有识别/拆解先生成可编辑草稿，保存前确认。GUI 全流程浏览器验收尚待阶段 08。
- 依赖探针发现最新 jsdom 需要 Node 22.22.2；该补丁下载失败，固定 jsdom 26.1.0（支持 Node 22.22.0），保持 Node 22 技术栈。

## 阶段 07–09 验证

- 真实 Deep Agents 工厂 + 精确 11 个业务工具 + 持久化 AsyncSqliteSaver 已实现；无文件/shell/task 工具。HITL 参数与服务端 approval capability 绑定，工具不能指定 owner_id。
- pytest 累计 24 passed，包括重启等待确认、重复批准只写一次、拒绝不写、过时草稿不写、SSE 游标回放、越权、计划旧 revision、停机双数据库/图片备份恢复、删除本人数据隔离。
- assistant-ui external store runtime 接 FastAPI SSE 编译通过；前端 Vitest 1 passed、扩展 Vitest 2 passed。
- Playwright Chromium v1248 / Chrome for Testing 156.0.8078.4：390/768/1440px 三条真实 API GUI 流程均通过，3 passed。模型为 tests/e2e_server.py 中明确测试替身；不构成模型验收。
- 跨端同一后端访问的部署文件、PS/POSIX启动脚本、停机备份脚本已实现；Docker/pwsh 本机不可用，模板未实机验证。默认独立本机两份数据库不自动同步。
- 阶段 03 扩展真实浏览器+模拟学校正在验证。阶段 10 真实学校/视觉模型/Windows/Edge/Safari仍未执行。
- 本次按 requesting-code-review 技能启动独立只读 reviewer；等待其反馈后修复重要问题并回归。

## 复核与回归（2026-10-15）

独立只读 review 后修复并补实测回归：第二次写入必须新审批；取消/过期导入草稿不能保存；缺年份/钟点/证据的截止保持待确认；分段同课程来源键不合并；旧区间安排避免重复耗时；重拆解清理未锁定旧块；慢模型等待释放数据库锁且返回时检查全局业务 revision；过期审批不能批准但可以拒绝释放线程；服务崩溃落在 checkpoint 与 approval 发布之间时恢复待确认。

保留计划块在生成前重验截止、课程/固定事项、学习窗口、容量、剩余耗时与依赖。失效未锁定建议列入 removed_blocks，校对后事务删除（含区间外）；锁定冲突保留并标明未安排原因，不能假算为截止前完成。

华工适配在 extension/lib/scut-list.ts，只白名单提取课程字段，再 DOMPurify -> lxml/pandas；固定主入口，限定精确 xsjw2018.jw.scut.edu.cn origin。本人选择学期点击查询、课表发生变化且学期与控件文本一致、稳定加载后才捕获；已写 GUI 操作提示。后端静态配置永不授权全量删除。

本次最终已运行：

- backend/.venv/bin/python -m pytest backend/tests -q：41 passed，6.04s。覆盖图片格式/大小/像素限制、鉴权隔离、版本/幂等、解析、任务DAG、排程、审批、SSE、恢复与备份。
- backend/.venv/bin/ruff check backend/app backend/tests scripts：All checks passed；uv lock --project backend --check：105 packages，成功。
- npm --prefix frontend run build：成功。按页面拆分后最大 chunk 359.25 kB（gzip111.70 kB），无先前大 chunk 警告。FullCalendar 全部6.1.20；新增官方 luxon3 6.1.20 + luxon3.7.2 支持设置时区跨设备显示。
- npm --prefix frontend test：1 passed（SSE解析）；npm --prefix extension test：4 passed（净化边界、实测结构/隐私排除、存储串行）。Vitest 测试范围显式限定 src，避免把 Playwright 用例当单测执行。
- 通用扩展 + 响应式 Playwright：4 passed，26.1s；专用布局用例按 profile 跳过一次，是分开构建后单独运行，并非漏验。
- 华工实测结构的虚构课程 Playwright：1 passed，36.6s，包含本人查询保护、选择第2学期、worker Target.closeTarget 重启、GUI刷新重绑、一次开页、自动预览与确认；不是实际学校 Chrome 验收。

实际运行环境命令前缀：Node22.22.0=/private/tmp/campus-node-runtime/node_modules/node/bin，Python=backend/.venv/bin/python，UV_CACHE_DIR=/private/tmp/campus-uv-cache，PLAYWRIGHT_BROWSERS_PATH=/private/tmp/campus-playwright。自动浏览器为 Chrome for Testing156.0.8078.4/Playwright1.64.1（Chromium1248），当前宿主 macOS arm64。

交付说明：README.md、docs/run-and-deploy.md、docs/scut-import.md、docs/acceptance.md。真实配置与测试配置分离；生产扩展最终使用 config/scut-undergraduate-2026-10-14.json 构建到 .output/chrome-mv3，测试产物仅在 .output-e2e。

补充最终 GUI 验证：assignment-chat.spec.ts：1 passed，4.7s，测试服务 FakeVision + 真实 API + Deep Agents ToolModel；本人校对前任务数0，多作业确认后2，Agent待批准时仍2，批准和刷新后3。测试图片明确为20x20合成 PNG，不是真实识别准确率。华工专用布局最后重跑：1 passed，16.0s；总计6条不同 GUI/扩展端到端用例通过（通用4 + 专用1 + 图片/批准1）。

生产扩展已最后构建并 typecheck 通过，manifest仅 storage/alarms 与 http://127.0.0.1:5173/*、http://xsjw2018.jw.scut.edu.cn/*；无测试学校域。服务已实际启动：127.0.0.1:8000真实API、127.0.0.1:5173 Vite GUI，健康200，未登录 /api/me 为401，已在 Codex 浏览器打开真实登录界面。学校适配配置已启用；模型尚未配置。后端和前端当前保持运行，进程退出后按 README 重启。

## 本人回复与 Luna 接入准备（2026-10-15）

- 本人确认第1周周一“8月31号”，结合实测学期记录2026-08-31；仍需节次钟点，并在本人助手账号设置中保存。
- 重新读取官方 OpenAI Docs：GPT-6 Luna 支持图片、函数调用、结构化输出；标准每百万 token 输入$0.10、输出$0.50（不超过272K输入），5.4 mini为$0.75/$4.50。没有据此宣称真实中文截图准确率或延迟优于5.4 mini。
- Luna 在推理模式下调用工具需要 Responses API。锁定 langchain-openai 1.7.2 的离线探针发现：只有工具绑定时自动路由不足以覆盖图片结构化输出；已对 OpenAI 的 gpt-6-luna 显式设置 use_responses_api=True、reasoning_effort=low。其他模型保持原路径，不自动切换更昂贵的模型。
- 新增两个 MockTransport 测试，使用实际锁定 SDK 的请求序列化和响应解析，覆盖 /v1/responses、图片 input_image、JSON schema、白名单函数、low 推理与不发送 temperature。仅离线协议探针，不等于真实供应商验证。
- 最新检查：ruff check backend/app backend/tests scripts 全部通过；pytest backend/tests -q：43 passed，6.36s。
- .env.example 更新低成本候选；本人尚在选择模型，未修改 .env 中现有型号，未填密钥、未进行计费调用。选择 Luna 时将 TEXT_MODEL 与 VISION_MODEL 改为 gpt-6-luna，填写 MODEL_API_KEY，重启后端后运行 scripts/verify-models.py。
- 官方来源：https://developers.openai.com/api/docs/models/gpt-6-luna ，https://developers.openai.com/api/docs/models/gpt-5.4-mini ，SDK来源：https://docs.langchain.com/oss/python/integrations/chat/openai 。

### OpenRouter 配置补充

本人明确使用 OpenRouter 后，核对其官方模型页与 Responses 文档：模型 ID 为 openai/gpt-6-luna，基础地址 https://openrouter.ai/api/v1，项目 MODEL_PROVIDER=openai 表示 LangChain 的兼容接口类型；MODEL_API_KEY 使用 OpenRouter key。

已将 Luna 的 Responses/low 配置扩展到带 openai/ 前缀的型号，避免仅原生名称生效。离线 SDK 探针同时覆盖两个渠道、文本工具和图片结构化输出，并验证 /api/v1/responses 与完整模型 ID。ruff 全部通过；后端45 passed，6.87s。未读取或打印本人密钥，未调用真实 OpenRouter；实际连通性、权限与准确率待填好配置后验证。

官方来源：https://openrouter.ai/openai/gpt-6-luna?view=api ，https://openrouter.ai/docs/api_reference/responses/overview 。

## 真实 OpenRouter 验收（2026-10-15，本人保存密钥后）

只检查配置项与密钥是否存在，不打印密钥。实际配置：openai 兼容接口、https://openrouter.ai/api/v1、文本/视觉均 openai/gpt-6-luna。后端已重启加载最新配置，127.0.0.1:8000 API 和127.0.0.1:5173 GUI保持运行。

实际运行与结果：

- backend/.venv/bin/python scripts/verify-models.py：exit0，真实文本工具调用成功；真实视觉接口提取合成图片中的两项作业，未注明截止时间的项目保持 null。合成英文测试图不代表真实中文截图准确率。
- 初次真实 Deep Agents 验收发现模型将保存工具误认为直接绕过确认，回复要求先批准尚未生成的面板；已修正 system prompt，明确调用工具只是提出操作、HITL 会在事务前暂停，不能自行批准，只有工具事务成功才能宣称保存。保留全部服务端确认校验。
- 恢复验收的首次同进程双 TestClient 遇到 Event loop is closed。诊断定位为锁定 LangChain SDK 的全局缓存异步 HTTP client 跨两个已关闭的测试事件循环复用；不是学校页面或模型拒绝。验收改为两个独立进程，符合实际服务重启，不修改生产传输逻辑来迁就测试。
- backend/.venv/bin/python scripts/verify-agent.py：exit0。真实 Luna -> Deep Agents -> list_tasks -> SSE 完成；模型 commit_import 请求暂停且任务数0；独立进程重启读取持久 checkpoint；测试客户端模拟批准两次，真实模型继续完成，仅保存1项虚构任务。隔离临时目录自动清理，无生产账号/任务改动。脚本可重复运行，但会产生真实 API 费用。
- 额外真实 ModelGateway.decompose_task：中文虚构800字阅读报告，StepProposal 校验通过，覆盖非空步骤、5–240分钟估计、非空完成标准、存在且无环的依赖；无学生任务写入。结构化有效不等于耗时估计已由学生验证。
- 最后检查：ruff check backend/app backend/tests scripts 全部通过；pytest backend/tests -q：45 passed，7.23s。
- 运行中服务最后检查：GUI200；/api/healthz 200且model_configured=true、vision_configured=true、scut_verified=true；未登录 /api/me 401。进程退出后按README重启。

仍为 external_input_required：本人实际中文作业截图与字段人工校对、1–12节钟点、目标Windows/macOS Chrome/Edge真实扩展学校全流程、Safari Web与同后端双设备。学校DOM已有本人登录实测、模型已有真实接口调用，不能将这些扩大成全部设备或真实截图准确率已验收。

## A方案：本地桌面入口与导入向导（2026-10-15，实施中）

本人已明确批准A方案执行。设计与逐项计划：docs/superpowers/specs/2026-10-15-local-desktop-design.md、docs/superpowers/plans/2026-10-15-local-desktop-plan.md。本地模式为默认；保留shared账号模式供自行选择同后端部署，桌面启动器强制local且仅监听127.0.0.1。未读取或打包现有密钥。

- 本地身份使用现有FastAPI Users DatabaseStrategy/CookieTransport，Alembic0002存储选定资料。新库自动个人会话，旧库显式选择，禁止隐式合并、删除或切换资料。Host/Origin/回环peer与CSRF仍检查；local下注册登录路由关闭。首轮后端50 passed，7.08s。
- GUI增加LocalEntry及本地模型设置，不回显密钥、留空保留；固定扩展目录查询/打开、可控服务停止。新增Radix Dialog 1.3.1（锁定）提供焦点管理和Esc关闭。
- 本地GUI测试先RED再GREEN。真实浏览器暴露Vite8默认代理改写Host为8000的问题，已显式保留5173 Host，不放宽后端校验。local-mode.spec.ts：1 passed，9.6s；390px直接进入今日、刷新owner不变、无扩展详细引导、扩展未安装时导入会话为0、模型密钥空白均通过。此测试仍使用明确标记的隔离测试服务器，不是学校实机验收。
- PyInstaller 6.22.3 + hooks-contrib2026.8已锁定安装，uv现112包。启动器纯逻辑4个测试先因模块不存在RED，再4 passed：项目.env/数据保留、分发版独立目录、不读取环境变量重定向、扩展稳定目录、数据指纹/固定参数。
- 正在构建原生macOS arm64桌面包；Windows提供原生构建脚本与手动CI job，未运行Windows，不宣称双系统实测。

### A方案集成与独立复核

- 原有共享模式GUI回归：5 passed，34.5s（图片校对/Agent批准、通用扩展fixture、390/768/1440px）。本地模式实测布局fixture：1 passed，19.5s，含向导继续、重复点击不重复开页、本人查询、worker重启、刷新、自动预览和确认。学校内容仍是明确合成fixture。
- 首个macOS arm64 onedir .app实际构建成功，约127MiB；verify-desktop.py在隔离目录、PATH=/usr/bin:/bin且无项目.env环境变量下实际通过：GUI静态资源、内置扩展精确权限、无模型密钥、个人会话、设置/owner重启持久化、重复启动同PID、恶意Origin403、正常停止。后续复核修复需重构建再验证最终产物。
- 按executing-plans要求完成一次fresh-context只读复核，无公开部署/真实模型/学校操作。发现并修复三项重要问题，均先复现失败再修复：源码启动扩展目录与源码树冲突（改稳定desktop-extension目录、源码保留测试）；Windows os.kill(pid,0)并非POSIX存活探测（改Win32 OpenProcess/WaitForSingleObject且关闭句柄，控制流测试禁止Windows分支发信号）；Pydantic模型级错误会回显输入密钥（统一422只返回type/loc/msg，合成密钥错误测试）。官方依据：https://docs.python.org/3.12/library/os.html#os.kill ，https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject 。Windows接口控制流单测不冒充Windows设备运行。
- 另补模型设置版本摘要与现有store.mutate持久幂等收据，避免旧页面覆盖新配置；请求只存摘要，响应/收据无密钥。新增真实重复/旧版本测试先RED后GREEN。
- 修复后后端59 passed，7.23s，Ruff通过。GUI模型设置安全保存回归与最终包重构建进行中。

Ruling: 源码入口明确使用项目目录的原.env/数据，独立.app/.exe使用OS个人目录 — 防止把作者密钥打包、避免误读取任意源码 — 两个入口的资料不会自动同步，当前本人使用根目录双击入口。
Ruling: Windows与Intel Mac需要目标平台原生构建，不把arm64包标成通用包 — PyInstaller按OS/架构产出 — 当前交付macOS arm64产物，其他目标保留external_input_required。

### A方案最终交付（2026-10-15）

- 复核修复后的最终macOS arm64 .app已重新构建成功，并重新运行verify-desktop.py：PASS（静态GUI、精确扩展权限、无内嵌密钥、owner/设置重启持久化、同PID重复启动、Origin403、正常停机，无Python/Node运行PATH）。停机瞬间HTTP连接先关闭的正常情况已在验收脚本中处理；首次重跑因此脚本判断失败，服务实际已退出，修正后完整通过。没有把失败的脚本结果写成产品失败或隐藏。
- 最后后端pytest：59 passed，8.25s；Ruff全部通过；uv lock --check --offline：112 packages；前端build/typecheck成功，Vitest1 passed、扩展Vitest4 passed、生产扩展typecheck/build最后恢复实测华工配置。
- local-mode.spec.ts最后重跑：1 passed，10.7s，含合成密钥的错误脱敏、修正地址后保存、密码框清空。加前述共享5条、本地SCUTfixture1条，共7条不同GUI场景通过。390px向导截图已经实际检查，无水平溢出；内容可在弹窗内滚动。
- 产物：dist/desktop/课间助手.app（约127MiB）、课间助手-macOS.zip（63.3MiB）；ZIP SHA256 c6eff5371e00b86c774625b4f7d0e5b87270adfeb6a8b909dee636b8320e330b。扫描包内个人.env/model.env/campus.db/agent.db/sqlite文件为0。构建脚本用ditto保留macOS bundle权限/符号链接；原生CI配置未触发。
- 当前项目停机备份：backups/pre-local-desktop-2026-10-15.zip（双库/图片、不含.env）。再使用最终frozen程序、PATH=/usr/bin:/bin，--data-dir项目根目录 --project成功启动。核对启动前后.env与extension/wxt.config.ts摘要不变；真实健康200，mode=local，文本/视觉模型配置存在，未重复付费调用模型。
- 当前仅127.0.0.1:5173单个FastAPI桌面服务运行，静态GUI同源供给，无Vite/8000运行。已在浏览器打开“检测到已有资料”页，原资料尚未由程序自动选择、合并或删除；本人点击继续使用即可绑定，之后免登录。user_selection_required仅为一次资料选择，不需要学校/应用密码。
- 当前用户入口：根目录启动课间助手.command（Mac）；Windows原生构建后的启动课间助手.cmd。独立.app使用OS个人目录、项目入口保留原资料；详见docs/desktop.md。没有发布、推送、签名公证、安装用户浏览器扩展或操作学校业务。
- external_input_required仍包括：Windows/Intel Mac原生设备与实际Chrome/Edge学校流程、真实中文作业截图人工准确率、节次钟点、Safari/多设备共享模式实测。本次A方案本地实施/本机验证完成，以上外部验收没有冒充已完成。

## 新开课表标签页未关联（2026-10-15）

- 本人报告已打开真实华工课表但助手未自动导入。只读检查发现真实 Chrome 课表容器23条、学期2026-2027第1学期；助手扩展已连接，但数据库导入仍 waiting_login、draft_id为空。后台仅接受初始 schoolTab，没有处理教务菜单新开的子标签页。
- 先增加明确合成的 portal → window.open 课表回归，旧实现失败：查询后20秒无预览，后端仍 waiting_login。修复采用浏览器真实 openerTabId 祖先链，精确学校 origin/课表路径、顶层消息、有效会话均校验；保留根标签和已关联标签到 storage.session，不增加权限，不接管无关已有学校页。更新扩展版本0.1.1。
- 首轮安全回归暴露测试环境干扰：Chromium 为 context.newPage 自动设置当前活动学校页为 opener，所谓“无关页”实际成为子页。查看隔离测试的 tabs/绑定后，将无关页改为在导入入口建立前创建，不改变生产授权逻辑迁就测试。修正后的 local + SCUT fixture 两种同页/新页全流程：2 passed，39.8s；覆盖本人查询前无草稿、无关页不采集、MV3 worker重启、GUI刷新、预览、确认保存。不是实际学校全流程验收。
- 扩展 Vitest4 passed，typecheck通过；前端 Vitest1 passed、build通过。向导和学校说明补充新标签页自动关联、保留入口到预览。
- 浏览器安全策略禁止自动进入 chrome://extensions/，因此不能替本人点扩展“重新加载”；不绕过限制。实际浏览器仍需加载更新文件后刷新助手、重发已过期导入，在教务菜单打开课表、选择学期查询，确认真实预览。
- 最终后端59 passed（8.04s）；macOS arm64包重新构建成功，verify-desktop.py完整PASS。最终生产扩展typecheck/build再次通过且background.js与包内逐字节一致。已以原项目资料恢复127.0.0.1:5173服务，desktop-extension已更新0.1.1；浏览器中已加载的旧扩展仍须本人重新加载，未宣称真实课表已提取或保存。

## 实时日期 MCP 与“明天有什么课”（2026-10-15）

- 本人要求复用开源日期MCP，修复Agent误把8月30日当今天的问题。排查原工具白名单只有11项，无时间工具；静态系统提示未注入真实日期，设置中的学期锚点会与当前日期混淆。
- 核对官方文档与安装源码后，采用未修改的官方MIT mcp-server-time，经LangChain MCP Adapters固定本机stdio连接；源码最小兼容探针实际返回Asia/Shanghai当前日期。安装锁定：mcp-server-time2026.10.10、langchain-mcp-adapters0.3.2、mcp1.30.0（限定>=1.29,<2）、tzlocal5.4.4；uv解析124包。初次系统Python查PyPI证书失败、httpx经环境代理超时；最终uv正常解析安装，未关闭TLS校验。
- 新增get_current_time只读工具，身份/时区由后端已登录资料注入，工具白名单12项，无任意命令/服务器URL；每次模型调用前动态提示经真实MCP刷新today/yesterday/tomorrow，禁止用开学日期或旧聊天记录推断今天。时间失败显式报错，不猜测日期。截图相对截止仍使用本人校对消息日期。
- RED：工具清单测试因缺get_current_time失败；时间失败提示回归先因旧泛化错误失败。GREEN：62 passed，15.38s；覆盖真实官方MCP日期与非法时区、不同用户设置时区注入、旧8月30日记录、跨午夜明日变化、重启延续、实际课程查询结果、时间失败时不调用模型。测试时钟/模型仅在明确测试中使用。
- 增加桌面--time-mcp入口运行原官方服务器，恢复windowed程序的真实管道stdio；不要求安装额外运行环境。PyInstaller打入MCP依赖/元数据，macOS arm64重构建成功，verify-desktop.py实际PASS：包内官方MCP通过stdio返回当前时间、PATH无Python/Node、GUI/资料持久化/同PID重复启动/Origin拒绝/正常停止。
- 真实OpenRouter Luna验收：scripts/verify-time.py，以虚构课表/隔离库和明确测试旧错误日期记录询问“明天有什么课？”。首次模型运行已完成，但脚本读取底层checkpoint channel_values不存在messages而失败；改用公开graph.aget_state重跑，不改生产恢复逻辑。最终PASS：真实模型调用get_current_time，再以start_date=end_date=2026-10-16调用list_course_occurrences，回复08:00–08:45虚构时间验收课程；无学生任务写入。两次运行有少量真实模型费用。
- 已核对旧服务无活动Agent任务后重启，使用原项目.env/数据库/聊天历史，新桌面包已在127.0.0.1:5173运行。用户无需改.env或重载课表扩展。新增说明docs/time-mcp.md；Windows实机仍external_input_required，不把macOS验证扩大为Windows运行证据。
- 官方来源：https://github.com/modelcontextprotocol/servers/tree/main/src/time ，https://docs.langchain.com/oss/python/langchain/mcp 。
- 最后复验：Ruff通过；uv lock --check --offline解析124包通过；完整pytest62 passed，14.83s；运行中桌面health确认local、模型配置存在。最终macOS桌面包含最新动态日期提示与MCP服务器，用户刷新助手即可继续原聊天。

## 流式回复与自然语言新增任务（2026-10-15）

- 用户要求真实流式输出、自然语言添加任务。已检查现有 FastAPI SSE、LangGraph 图、assistant-ui 外部 runtime、草稿/确认服务；原后端仅在模型回答完成后发送整条 message，前端 Set 去重会丢弃同一消息的后续文本。方案与验收见 docs/superpowers/plans/2026-10-15-streaming-tasks.md。
- 复用已锁定 LangGraph messages/updates 双流及 assistant-ui 外部 runtime，不加新依赖。后端仅发布主聊天模型可见文本，过滤 reasoning/工具参数/嵌套工具模型；首片段立即入库，后续50ms或64字符合并，最终文本与片段共享唯一ID。前端归并增量、用最终消息替换部分消息，按持久游标去重；短暂断线带游标自动重连，持续失败给出重新连接入口。刷新期间运行完成后重新读取状态，防止恢复后一直显示生成中。
- 自然语言任务明确调用 create_assignment_draft，允许省略要求/截止日期，保留 due_text/submission_method，截止无具体钟点保持 due_at=null 和待确认提示。助手展示“核对任务草稿”，支持编辑标题、要求、课程、提交方式和截止时间，仍经真人确认事务才创建学生任务，复用鉴权、版本校验和幂等保存。
- RED：延迟模型尚未结束时没有 delta；自然语言 due_text 丢失；前端断流后不重连。修复后完整 pytest：64 passed，16.89s；Ruff通过；uv lock --check --offline解析124包通过。Vitest：3 passed，覆盖增量/重复/最终文本、断线续传；前端类型检查/生产构建成功。首次组合内容测试还暴露内容列表含字符串时最终文本丢失，已修复并保留回归。
- Playwright隔离测试服务器/明确测试模型：chat-stream-task.spec.ts 1 passed，10.2s，390px验证第一段出现时 run 仍 running、未出现第二段、生成中刷新恢复且只一条、结束恢复发送、自然语言草稿尚无任务、编辑后确认、刷新仅一项、无水平溢出。原 assignment-chat.spec.ts 1 passed，8.0s，截图校对/Agent HITL批准保持。首次新测试误把 assistant-ui 自带生成指示点当多余文字，改断言为部分内容存在且后半段不存在；首次旧测试从根目录启动导致fixture相对路径找不到，改在frontend目录重跑。未将这些失败隐藏或扩大为真实模型验证。
- 真实 OpenRouter 已配置 Luna + Deep Agents + 官方Time MCP：scripts/verify-chat.py PASS，实际调用 create_assignment_draft，真实回复产生6个持久化文本增量，逐条合并与最终回复一致。草稿“阅读两篇文献，记录关键结论”，due_text=明天、due_at=null；隔离库学生任务仍0，无生产资料写入。此脚本会产生少量真实模型费用。
- 桌面包正在重构建；完成后将运行原生无运行环境PATH自检并恢复项目服务。扩展无修改，无需重新加载扩展。
- 最终交付：macOS arm64桌面包与ZIP重新构建成功；verify-desktop.py PASS（内置官方MCP stdio、无Python/Node运行PATH、静态GUI/扩展无密钥、个人资料重启持久化、重复启动同PID、Origin拒绝、正常停机）。已使用原项目资料启动更新后的127.0.0.1:5173服务，health=ok、mode=local、模型配置存在，实际HTML加载最新index-De1j9xxT.js。本人刷新助手页即可使用。此次未改.env、未新增依赖或扩展权限；Windows实机及其他原有外部验收仍external_input_required，不扩大本次macOS证据。

## 日程与待办可见性、七天计划空白（2026-10-15）

- 本人截图反馈助手出现无关导入说明、看不到新增日程/待办、七天计划只有空确认卡。只读核查生产库：有1条已保存“参加院运会彩排”任务、0步骤、0固定日程、0学习块；起止时间误放在 due_text，另有同名待确认任务草稿和多个空计划。原 Calendar 只请求课程，Chat 总渲染 BrowserImport；planner 只遍历步骤，没步骤的任务被静默遗漏。此次不自动改写、转换或确认这些原资料。
- 计划：docs/superpowers/plans/2026-10-15-calendar-events.md。复用已有 fixed_event/Pydantic、草稿确认、版本/幂等事务、FullCalendar、assistant-ui与LangGraph，未加依赖。新增 calendar_event 草稿、create_calendar_event_draft 和 list_calendar_events；实际图工具白名单14项，无shell/文件/通用浏览器。工具区分明确起止的活动与仅截止/无时段的待办；相对日期仍用官方Time MCP。修改未确认日程用id+revision更新同一草稿，用户确认前无固定日程。
- 新日程聚合接口按用户/时区/范围返回课程、固定事项、学习块；缺课程钟点只显示警告，不遮蔽其他日程，跨午夜事项按重叠判断。课表页可直接和同一个流式助手对话，确认后刷新日历并打开对应周；三类不同颜色，可点开详情。24小时均可查看，桌面日历内部滚动。助手日程保存也会转到对应课表日期。
- 导入桥接只在登录后的 Workspace 挂载一个，始终能接收Agent导入请求；普通助手不再常驻学校导入提示/历史成功卡。课表页和实际进行中的导入保留状态、向导及恢复。
- 导航改为“待办 / 作业”，已保存内容提前显示；今日、课表都有“我的待办”，保留原始时间描述和未确认草稿提示。无步骤待办可填本人预计分钟，通过既有可编辑步骤草稿和确认事务再参与规划，也仍可请AI拆解。无估计不擅造耗时。
- 排程对没步骤的任务返回标题及“尚无可排程步骤，请填写预计耗时或确认任务拆解”，并在七天预览列出已固定的课程与活动；无学习块显示明确原因和下一步，没有内容不展示保存按钮。新计划将旧待确认计划标为superseded，保留历史；旧版本界面也只展示最新待确认计划，防止多张空卡堆叠。
- RED：日程草稿405；无步骤任务未安排列表为空；工具名单缺日程工具；课表无自然语言入口；没有学习任务时缺固定日程预览。修复后完整后端70 passed，21.07s，Ruff通过。覆盖确认前无日程、重复确认单写、旧revision拒绝、所有者隔离、修改同一草稿、跨午夜、课程配置错误不隐藏日程、无步骤原因、旧计划替换及原排程/鉴权/流式恢复。
- 明确测试模型/隔离库GUI：课表自然语言日程→校对→保存→刷新、今日及课表待办可见、缺耗时解释→45分钟步骤校对保存→实际七天时间块→保存到日历；另从助手保存两周后事项自动定位正确周。首轮2 passed，10.3s。原截图/HITL及390/768/1440px任务/拆解/排程/聊天回归4 passed，18.0s；流式生成中刷新与本地免登录/模型配置/向导2 passed，18.8s。初次浏览器命令工作目录误用未执行测试，修正后先复现入口缺失；旧手工草稿测试标题改为现有“核对任务草稿”。这些测试模型不代表真实学校/供应商。
- 真实已配置 OpenRouter Luna + Deep Agents + 官方Time MCP：scripts/verify-chat.py --calendar PASS，9个真实文本增量与最终内容一致；“明天17:30开始，持续两小时参加院运会彩排”生成2026-10-16 17:30–19:30+08:00日程草稿，而非待办；隔离库fixed-events/tasks均0（未自动批准）。未向模型发送此次生产库核查内容；少量真实调用费用。
- 最后GUI复验：calendar-todos.spec.ts 2 passed，11.1s（包括固定日程预览和跨周跳转）；合成SCUT同页/新页流程2 passed，约1.1m，覆盖全局桥接、本人查询前不采集、MV3重启、GUI刷新、预览与确认。与前述4条共享流程、2条本地/流式流程共10条不同GUI场景通过。已实际检查390px七天预览和课表/待办截图，日程与学习块均可见，无水平溢出；截图为测试数据，不能当生产用户日程。
- 前端最终Vitest3 passed、类型检查/生产构建通过；uv lock --check --offline仍124包。后端最终70 passed（21.07s）；无依赖升级。最终macOS arm64应用和ZIP重构建成功，正在完成原生自检后恢复原项目服务。
- 最终原生 verify-desktop.py PASS：内置官方MCP stdio、无Python/Node运行PATH、静态GUI/扩展、包内无个人密钥、资料重启持久化、重复启动同PID、Origin拒绝及正常停机。已以原项目资料恢复127.0.0.1:5173，health=ok/local/模型配置存在，实际服务返回最新index-R3kI9ygx.js。只读核对本机已选资料仍包含原“参加院运会彩排”待办；未自动改成新日程、未确认任何业务草稿。用户刷新页面即可使用，无需改.env或重新加载扩展。Windows与其他原有外部验收范围不变，不能把macOS及合成扩展测试当跨系统或真实学校新验收。

## 删除待办与草稿（2026-10-15）

- 本人要求补齐删除功能。读取现有 task/draft、关联步骤/计划块、浏览器导入及确认事务；沿用 SQLAlchemy/SQLite 短事务、CSRF/身份、revision 和 Idempotency-Key。新增 DELETE /api/tasks/{id}、DELETE /api/drafts/{id}，同一请求重试返回历史回执，不重复写入；没有新依赖、没有给模型开放删除工具。
- 待办删除事务清理其步骤和所有学习安排（含锁定/已完成），关联待确认拆解与按旧任务集合计算的计划标记失效；保留其他待办/已保存安排、课程、共享图片和历史确认回执。草稿删除保留 status=deleted 墓碑、从待确认列表隐藏，禁止旧确认或编辑恢复；五类草稿及空计划均支持。课表导入草稿删除同步取消 BrowserImportSession，修复原捕获内容相同分支在取消后仍返回草稿的情况；取消后的新捕获拒绝409。
- GUI 复用已锁定的 Radix Dialog 1.3.1、shadcn Button、TanStack Query 5.104.2；今日/课表/待办卡片增加“删除待办”，共用草稿操作区增加“删除草稿”。弹窗显示标题和关联影响，确认前不写入；冲突后必须刷新再确认，成功后所有相关查询同步。390px截图已实际检查，无水平溢出。使用方法与独立验收命令见 docs/acceptance.md。
- RED：后端删除请求405；GUI等待“删除草稿”超时。GREEN：新增10项后端测试覆盖五类草稿、已确认保护、鉴权/CSRF/owner、旧revision、请求重放、跨重启、关联清理、取消捕获、旧Agent批准不能保存已删除草稿。完整 pytest 80 passed（25.49s），Ruff全部通过；前端Vitest3 passed，typecheck/build通过。同步重新生成OpenAPI及TypeScript接口。
- 独立删除GUI场景2 passed（7.8s）：取消/确认、刷新后仍删除、日历块清理、空计划删除及旧版本拒删后刷新重试。日程/待办旧GUI 2 passed（4.5s/2.3s）。曾将两个local场景文件拼接运行，前一个用例保留的“阅读文献”使空计划前提不成立而失败；改回独立临时服务后通过，未改生产排程规则来迁就测试。
- 原生验收脚本增加合成待办/草稿删除及服务重启后的幂等检查；准备将最新代码打入macOS arm64包，再恢复原项目资料服务。开发/GUI测试全用隔离库；没有删除本人任何记录，没有新付费模型或学校调用。
- 最终共享模式截图/HITL、390/768/1440px保存/拆解/排程/聊天回归4 passed（19.2s）；OpenAPI和TypeScript类型重新生成，最终前端生产build成功（index-C0WQW_m9.js）。macOS arm64 .app/ZIP重构建成功；增强后的 verify-desktop.py PASS，实际原生程序验证任务/草稿删除、重启后的请求回放、官方Time MCP及原有运行环境/安全检查。
- 已用新桌面程序恢复原项目127.0.0.1:5173服务，health=local且模型配置存在，实际提供最新静态GUI和两个DELETE接口。只读比较更新前后全部 task/step/plan_block/draft/course/fixed_event/settings 数据摘要、本机选定资料、.env摘要完全一致；本人原待办/草稿未删除。使用现有入口，刷新即可，无需改模型或重新加载扩展。Windows/Intel Mac及原有真实学校外部验收边界保持不变。

## 自然语言更新已确认待办截止时间（2026-10-15）

- 本人反馈自然语言无法修改已确认任务的截止时间。排查真实图工具：原14项仅有set_task_status可更新已保存任务，截止字段只在创建草稿和手工PATCH中可写；不是模型供应商或时间MCP失败。先将实际工具清单回归加上目标能力，旧实现因缺set_task_deadline失败。
- 新增set_task_deadline（第15个白名单工具）并加入原LangGraph HITL写操作集合。先list_tasks匹配ID/当前版本，相对日期核对官方Time MCP；工具参数必须明确日期钟点、时区、正式/补救截止类型。类型字段必填，确保待确认参数与执行指纹一致；身份由后端注入，不能模型自行授权。保存走与手工PATCH共用的apply_task_update领域服务，Pydantic验证、事务、版本及原幂等回执全部保留。无新依赖。
- 确认正式截止后移除due_at不确定标记并清除旧补救日期；显式补救操作保留原截止。使旧待确认计划和关联拆解失效，已有步骤/锁定块/学习安排保持，需要本人重新规划。提示词要求重名不明确时询问、不新建同名任务、缺钟点不猜23:59。
- GUI确认面板显示真实待办标题、版本、原/新时间、本人设置时区、旧补救时间清除及规划影响。联调复现刷新后批准虽已保存但确认卡重现：历史重放遇approval_required提前结束，且重读run时不区分status便恢复其历史approval_id。先加SSE回归（原只返回第1条，丢失后续消息/done）并复现GUI，再修复为读到done/error或真实waiting_approval结束；仅待确认状态展示批准，恢复后及时清空，完成后刷新不重复要求确认。
- 新增8项后端测试：待批准不写、拒绝、旧版本、已删除、时区/授权/owner、重启恢复及重复批准、明确正式/补救截止、旧补救清理、保留步骤/锁定块、模糊钟点询问。完整pytest最终88 passed（28.30s），Ruff通过。第一次完整运行与Vite构建并行，assets目录清理瞬间导致StaticFiles目录不存在（1 failed/87 passed）；构建后重新完整执行通过，没有为测试竞争改生产行为。
- 前端Vitest4 passed（含新增历史批准回放），类型/生产构建通过（index-Cr6raZ-y.js）。390px截止GUI1 passed（10.7s），覆盖待确认刷新、批准后同一任务更新、再次刷新历史无重复批准；实际检查手机截图。共享截图/HITL和390/768/1440px拆解/排程/聊天原流程4 passed（20.3s）。夹具和固定测试时钟仅测试使用。
- 真实已配置OpenRouter openai/gpt-6-luna + Deep Agents +官方Time MCP，scripts/verify-deadline.py PASS：普通中文“请把截止探针报告的截止时间改为明天晚上8点”，实际get_current_time → list_tasks → set_task_deadline，提出2026-10-16T20:00:00+08:00；批准前记录不变，批准后原ID/版本+1，数据库只有1个合成任务。仅独立临时库，无本人业务资料或学校调用；一次小额真实模型验收。
- macOS arm64 .app/ZIP正在重构建；原生验收脚本增加新工具清单及截止领域服务检查，之后恢复原项目服务并核对资料摘要。原有Windows/Intel Mac及学校外部验收边界不变。
- 最终流式刷新/本地入口回归2 passed（18.0s）；本次7条GUI场景通过。macOS arm64 .app/ZIP构建成功；增强后的verify-desktop.py PASS：15工具声明、明确截止字段更新/不确定标记清除、删除与重启幂等、内置官方MCP及无Python/Node运行PATH等原检查。
- 恢复检查第一次脚本误断言本地session返回200（实际正常为204）；随后终端启动的后台服务已退出，未将其写成恢复成功。改用macOS正常open -n启动.app后，真实health=local/模型已配置，最新index-Cr6raZ-y.js/Chat-DO2qdVJc.js均可读，认证后/api/agent/tools实际图检查15项且包含set_task_deadline。只读核对全部业务资源、选定资料及.env摘要与更新前一致，未改本人任务截止。当前本机服务已恢复；用户刷新后直接提出截止修改并批准即可，无需更换模型或改密钥。


## 草稿响应式、聊天空间、连续保存与自然语言日期（2026-10-15）

- 本人两张截图反馈四项问题。按既有流程作有界修复：无截图的AssignmentReview仍用固定双栏造成空半栏；assistant-ui Composer是form，受到全局form max-width:700px限制；大标题和长说明挤占聊天高度且挤窄新会话按钮；commit_draft对所有草稿一律检查settings全局revision，保存第一份导致无关第二份409；Agent只有修改已保存任务的工具，没有查询/修改待确认作业工具。
- 先复现：连续保存第二份409、教学周due_at仍null、缺草稿编辑工具；布局实测字段只占卡片46.9%。新增测试后分别修复。改为独立作业/日程可连续保存，拆解由task_revision保护，计划/课表仍保留全局来源版本。原恢复测试用改动无关设置模拟失效与新规则冲突，改为真正修改被批准草稿，继续保证旧确认不能覆盖新版本。
- 界面复用原assistant-ui/表单组件，不增加依赖。助手紧凑工具栏和可伸展聊天区，输入框覆盖全部可用宽度；宽屏右侧独立滚动校对区，窄屏上下排列。无图草稿限制合理阅读宽度、移除空列，按容器宽度排字段；有图才在宽度足够时并排。草稿服务版本变化会刷新校对内容，解决对话已改而日期输入仍旧的问题。409保留后端具体原因。
- 新增确定性教学周边界服务，基于已保存首周周一/学期范围/时区计算。第14周之前=2026-11-30 00:00+08:00；11周之前=2026-11-09 00:00+08:00（首周2026-08-31）。这是周开始前的边界，不补23:59；模糊日期/周末/缺锚点/越界仍不猜。草稿记录deadline_basis，确认时校验学期依据；手动修改明确日期清除旧推算。旧草稿GET仅附suggested_payload，不写业务数据；本人确认时才用PUT/confirm保存。
- Deep Agents实际白名单18项：新增list_assignment_drafts、set_assignment_draft_deadline、resolve_academic_deadline。用户修改待确认草稿时查询真实id/revision/item_index，保留截图引用和其他作业项，持久幂等回执支持相同工具调用重放；旧版本或其他用户不能覆盖。正式任务截止仍复用HITL，教学周可先查确定性边界再提出更新。
- 完整pytest97 passed（25.49s）；Ruff通过；uv lock --check --offline解析124包通过。前端Vitest4 passed，typecheck通过；OpenAPI及TypeScript契约已重新生成。无新增依赖，沿用锁定React19.3/Vite8.3.4/assistant-ui0.15.28等版本。
- Playwright：新布局390/768/1024/1440px连续保存1 passed；教学周自动填日期、对话编辑原草稿、刷新、两份保存1 passed。共享模式截图/拆解/排程三个宽度4 passed；删除2 passed；已保存截止批准1 passed；流式刷新与本地入口2 passed。第一次把要求local模式的删除测试与shared测试合并，2项停在登录页超时；查明测试模式后独立local命令2 passed，没有修改产品绕开登录。布局初次修复测试因新增外层section使section定位匹配两张草稿，改外层div保留现有校对语义，后续通过。
- 真实已配置OpenRouter openai/gpt-6-luna + Deep Agents +官方Time MCP：scripts/verify-academic-drafts.py PASS。普通中文两项作业实际调用2次create_assignment_draft，日期与教学周边界一致；随后“把C++大作业草稿截止改成明天晚上8点”实际get_current_time→list_assignment_drafts→set_assignment_draft_deadline，原草稿revision+1、截止2026-10-16T20:00+08:00，无重复草稿；确认前任务0，之后连续确认2条。仅临时合成库，不改本人任务；一次两轮真实模型验收，有小额调用费用。
- 已检查桌面与390px测试截图；macOS桌面包/ZIP重构建及原生验收、原资料恢复待最后完成。扩展和.env无需更改；Windows/Intel Mac/真实学校等原有external_input_required边界不变。

- 课表嵌入聊天/未来日程定位回归2 passed（10.4s），本轮13条GUI场景通过。最终生产构建通过：index-gnc73b6I.js、Chat-QbKMRHL3.js、index-ikQWKn8k.css；macOS arm64 .app和ZIP构建成功（约34s）。原生自检增加包内教学周推算和独立草稿连续确认测试，正在运行。

- 最终原生自检PASS：新macOS包内官方Time MCP、无Python/Node运行PATH、教学周日期、独立草稿连续保存、删除重启幂等、个人资料持久化、重复启动同PID及Origin拒绝全部通过。使用macOS open -n正常恢复原项目资料服务，真实HTTP确认local/模型已配置、最新index-gnc73b6I.js与Chat-QbKMRHL3.js可读、认证后实际图白名单18项。全部原业务资源、选中资料和.env摘要与更新前逐项一致；未替本人保存、删除或改期任何任务。本人刷新127.0.0.1:5173即可使用。证据见/private/tmp/campus-usability-pytest.log、campus-academic-real-model.log、campus-usability-native-check.log；macOS本机结果不扩大为Windows实机验证。


## 普通月日“之前”仍要求手填截止（2026-10-15）

- 本人截图原文是“11月1日之前”，并非教学周。已确认前次仅支持教学周边界，普通月日被统一当成缺钟点留空。补充确定性日期边界：中文月日/明确年份/ISO日期及“今年、明年、今天、明天、后天”的“之前/前/结束前”，用标准datetime/date/ZoneInfo验证日期并计算边界，不补23:59；仅说日期或“左右/周末前”仍不猜时刻。
- 无年份的聊天/手录草稿按消息创建日期补全，原来源保存reference_time；旧草稿GET按created_at（SQLite无时区值按UTC解释后换到本人时区）生成只读建议，刷新/跨年不改变年份。原始截图只有本人确认的reference_time才可补年份，未提供则保持待确认；截图作业流程保留此来源。新增CalendarDeadlineBasis与原AcademicDeadlineBasis兼容，确认时重算核对，手动改日期清除旧推算依据。
- GUI明确显示“按消息日期…补全年份/相对日期”“已自动填写，直接校对后保存”。普通月日不会再显示首周undefined；保留编辑入口，明确日期不需要再手动操作控件。Agent提示与现有工具同步支持月日日期边界；resolve_academic_deadline名称保留以兼容旧检查点，实际也可解析普通日期，白名单仍18项。
- RED已复现7项失败（5种边界空值、旧草稿缺建议、Agent草稿编辑无日期）；修复后专门日期/教学周测试21 passed，新增截图消息年份与人工覆盖校验回归后最终完整测试结果见下文。前端Vitest4 passed、Ruff通过；OpenAPI/TypeScript契约已更新，无新增依赖。
- GUI隔离本地库：calendar-deadline.spec.ts 1 passed（5.9s），390px检查自动填入本年11月1日00:00、显示推算依据、确认前任务0、不操作日期控件即可保存、刷新同一任务。原教学周/自然语言草稿修改/多份保存GUI1 passed（8.2s）。已查看截图验证不再空白。
- 真实OpenRouter Luna/Deep Agents/官方时间MCP验收：scripts/verify-academic-drafts.py --calendar-boundary PASS。普通中文“帮我增加一个待办：11月1日之前完成日期边界验收报告”，实际get_current_time→create_assignment_draft，草稿due_at=2026-11-01T00:00:00+08:00；确认前任务0、临时库确认后1条，无需手工输入日期。仅一次真实模型请求，有少量调用费用，不操作本人的业务资料。
- 正在构建更新的macOS .app/ZIP并扩充原生自检，以原项目资料恢复服务后会核对原数据/.env摘要及真实旧草稿建议。

- 最终完整pytest112 passed（27.40s），包含15项本次日期边界回归：普通月日/年份/相对日期边界、旧草稿跨年稳定且GET不写、无界/非法日期保留空、图片仅按本人确认消息日期补年份、Agent修改原草稿及推算冲突/人工覆盖。前端4项Vitest与生产构建通过；macOS桌面包正在重构建。

- 生产构建成功（index-BKN6HesH.js、Chat-DfRG1QdL.js），macOS arm64 .app/ZIP重构建成功（约32s）。原生检查已新增普通月日“11月1日之前”自动日期/确认保存案例，正在运行；测试截图见/private/tmp/campus-calendar-boundary-review.png。

- 最终原生自检PASS：包内普通月日自动日期/确认保存、教学周、官方Time MCP、自带运行环境、持久化/删除幂等及Origin等检查通过。已正常恢复原项目服务，真实HTTP读取最新index-BKN6HesH.js，认证后实际18工具图可用。原业务资源、选中资料、.env摘要与暂停前完全一致。
- 恢复后只读核查截图日期：原库有两份due_text=“11月1日之前”的草稿，但状态均已deleted，当前pending列表无此项；未恢复已删除草稿，也未替本人新增待办。仍待校对的旧草稿兼容由专门临时库测试验证；新建此日期草稿的真实模型/GUI/原生路径均已通过。本人刷新页面后可直接自然语言生成带日期的草稿。Windows/真实学校等既有external_input_required边界未改变。

## 回到最新消息按钮不可达（2026-10-15）

- 本人截图反馈按钮一直跟随消息列表末尾，上滑后看不到。排查Chat.tsx将ScrollToBottom直接作为Viewport末尾的普通元素；已安装assistant-ui 0.15.28源码及官方Thread文档确认：该按钮到达底部只disabled，不会自行隐藏或定位。修复范围为现有组件的悬浮定位与disabled隐藏，继续复用框架滚动状态/点击/键盘/自动跟随，不新增滚动监听器或依赖。
- 验收：390px与1440px的真实长对话；空会话/位于底部隐藏；滚动阅读历史后按钮仍在可见消息区域内、无需滚到底即可点击；点击或键盘返回最新且隐藏，新会话清除按钮。增加chat-scroll.spec.ts使用明确合成消息、临时数据库与现有测试模型，不调用供应商或更改本人任务。
- 首轮测试因临时Playwright运行目录已被清理而未执行浏览器断言；正在恢复Chromium与项目Node22运行环境后重新复现。更新前已确认没有运行中的Agent请求、保存原业务资源/选中资料/.env摘要并暂停空闲项目服务，完成验证后恢复。
- Chromium恢复后RED：390/1440px均在空会话错误显示disabled按钮，断言失败（2 failed）。补上原生ViewportFooter的零高度sticky悬浮层、按钮定位、disabled不可见和键盘焦点样式后，原回归2 passed（11.1s）：上滑900px后坐标仍在消息可见区，直接按屏幕坐标点击返回，不依赖测试框架自动滚动；键盘返回/新会话/无横向溢出通过。人工查看两张截图确认布局。
- 现有流式生成中刷新恢复/自然语言草稿保存GUI1 passed（9.8s）；聊天/草稿390/768/1024/1440px布局GUI1 passed（3.9s）。前端全部Vitest4 passed、typecheck和生产build通过。使用Node22.22.0，业务依赖/后端/扩展/权限无变化；未重复收费调用模型。
- 当前产物index-C72-63-s.js、Chat-C-A2ui9X.js、index-DJ21haIW.css；正在更新macOS arm64桌面包，随后原生自检及恢复原项目服务。
- 最终本地模式限定后的按钮回归2 passed（11.4s）；macOS arm64 .app/ZIP成功重构建，原生verify-desktop.py PASS（内置官方时间MCP、无Python/Node运行PATH、静态GUI、持久化/删除/幂等/重启/Origin）。已正常恢复原项目服务，真实HTTP读取最新JS和悬浮/隐藏CSS成功，health=ok；全部原业务资源、选中资料、.env摘要与暂停前一致。本人刷新即可使用。原Windows/真实学校等external_input_required边界保持。
