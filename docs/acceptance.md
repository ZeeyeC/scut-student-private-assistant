# 验收记录与重跑步骤

## 本地自动化

业务测试直接使用临时 SQLite 和真实应用鉴权。FakeVision/ToolModel 只在 backend/tests，Playwright 使用显式测试服务器。测试从项目根目录运行：

```sh
uv run --project backend --no-sync pytest backend/tests -q
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix extension test
```

SDK 探针与 pytest 使用真正 Deep Agents 图和 SQLite checkpointer；模型为测试替身，验证工具清单、HITL、恢复、重复确认、版本冲突。不是供应商模型验收。

普通响应式 + 通用扩展 + 图片/批准 GUI 测试（macOS shell）：

```sh
cd extension
PUBLIC_ORIGIN=http://127.0.0.1:5173 SCUT_ADAPTER_PATH=../backend/tests/fixtures/test-adapter.json WXT_OUT_DIR=.output-e2e npm run build
cd ../frontend
npx playwright install chromium
npm run test:e2e
```

华工实测布局的虚构课表测试：

```sh
cd extension
PUBLIC_ORIGIN=http://127.0.0.1:5173 SCUT_ADAPTER_PATH=../backend/tests/fixtures/test-adapter-list.json WXT_OUT_DIR=.output-e2e npm run build
cd ../frontend
SCUT_E2E_LIST=1 npm run test:e2e -- extension-scut-flow.spec.ts
```

Windows 设置 `$env:SCUT_ADAPTER_PATH`、`$env:PUBLIC_ORIGIN`、`$env:WXT_OUT_DIR`、`$env:SCUT_E2E_LIST` 后执行同样 npm 命令；测试结束移除这些环境变量。测试包在 `.output-e2e`，不要将它当真实学校扩展安装。真实安装使用 scut-import.md 的 production 构建。

## 真实模型（协议已验收，真实截图准确率待验收）

根目录 .env 设置可用供应商 key、TEXT_MODEL、VISION_MODEL 后：

```sh
uv run --project backend --no-sync python scripts/verify-models.py
uv run --project backend --no-sync python scripts/verify-agent.py
```

该脚本会进行收费的真实工具调用和真实图片结构化调用，但图片是明确合成的双作业测试图，只验证能力与传输。再用真实中文作业截图人工比对：至少覆盖多作业、模糊日期、无年份、相对日期、无截止时间、课程同名；记录标题、要求、截止、课程关联字段结果，不能只检查 HTTP 200。相对日期要本人确认消息日期；无明确钟点保持待确认。

verify-agent.py 同样收费，使用临时隔离数据库和虚构账号/作业，调用真实模型检查业务查询、写入前 HITL 暂停、独立进程重启后的检查点恢复、重复批准只保存一次；测试结束删除临时目录，不修改生产学生数据。这是自动模拟用户批准的协议验收，真实用户仍需在 GUI 校对确认。

## 真实学校与设备（external_input_required）

分别在 Windows/macOS Chrome、Edge 验证：本人登录 → 选学期查询 → 自动预览 → 校对 → 确认一次。额外验证重复导入、GUI 刷新、worker 重启、取消、过期、窄屏和版本冲突；比较实际课程、周次、节次、地点是否完整。Safari 只验 Web 数据管理。

同一后端跨端：端 A 保存任务，端 B 刷新可见；同时编辑用旧 revision 应返回409；每台设备的学校导入只打开该发起设备的标签页。测试环境的账号隔离不能代替实际 Windows/Edge 验收。

## 恢复

停止服务，按 run-and-deploy.md 备份到新 ZIP、恢复到空目录。启动恢复目录，验证图片、课程、任务、Agent 待批准卡片和一次性批准；不得覆盖原目录。自动测试已经覆盖真实备份恢复后的暂停图继续执行。

验收证据和未完成项统一记录在 docs/progress.md；真实条件未满足时标 external_input_required。

## A方案本地桌面（2026-10-15）

新增后端测试覆盖自动个人会话、旧资料选择、Host/Origin/CSRF/远程拒绝、模型设置版本/重放/密钥脱敏、桌面目录隔离和非破坏性进程检查。Windows API分支使用测试桩，只验证调用逻辑，需在Windows设备/CI补原生验收。

本地免登录+未安装扩展向导+安全模型设置GUI：

```sh
cd frontend
CAMPUS_E2E_MODE=local npm run test:e2e -- local-mode.spec.ts
```

实测结构fixture扩展构建后可加 `CAMPUS_E2E_MODE=local SCUT_E2E_LIST=1` 运行extension-scut-flow.spec.ts；共享回归不设CAMPUS_E2E_MODE（测试服务器默认shared，不影响应用默认local）。

实际原生包自检和用户入口见 [桌面说明](desktop.md)。macOS arm64已构建运行；Windows与Intel Mac没有设备运行证据。阶段结果以progress.md最后一节为准。

## 日期 MCP（2026-10-15）

时间查询及“明天课程”真实模型验收见[日期 MCP 说明](time-mcp.md)。scripts/verify-time.py使用真实模型与虚构课表，会产生费用；scripts/verify-desktop.py增加内置官方MCP的stdio日期验证。日期工具不改变作业相对截止日期需要本人校对的规则。

## 流式回复和自然语言任务（2026-10-15）

新增后端 test_agent_streaming.py 验证模型未结束已有持久化文本、隐藏推理不泄漏、增量/最终文本一致、游标及服务重启重放、草稿保留模糊日期、确认前无任务、重复保存只一项。

浏览器回归（在 frontend 目录运行；使用明确测试模型/隔离库，不调用供应商）：

```sh
CAMPUS_E2E_MODE=local CAMPUS_E2E_CHAT_STREAM=1 npm run test:e2e -- chat-stream-task.spec.ts
npm run test:e2e -- assignment-chat.spec.ts
```

PowerShell用 `$env:CAMPUS_E2E_MODE='local'; $env:CAMPUS_E2E_CHAT_STREAM='1'` 设置，运行第一条测试后移除这两个变量，再运行共享模式旧回归。测试端口5173/8000须空闲。

真实已配置供应商验证（从根目录运行，收费，临时隔离库）：

```sh
uv run --project backend --no-sync python scripts/verify-chat.py
```

检查实际模型工具调用、真实文本增量与最终回复一致、模糊截止保留原文且时间为空、确认前学生任务0。正常使用：助手输入“帮我增加一个任务：明天阅读两篇文献，记录关键结论”，在聊天下方核对草稿，可修改字段，点击“校对完成，准备保存”再“确认保存”；作业页可见且重启后仍在。不给具体钟点不会自动填23:59；流式显示速度取决于供应商返回片段的节奏。

## 课表事项、待办与七天计划（2026-10-15）

课表点击“用 AI 添加事项”，例如“明天下午5:30到7:00参加院运会彩排”；校对具体日期/起止时间，确认后跳到对应日历周。只有待办或截止要求则生成任务草稿，在“待办 / 作业”及今日/课表的“我的待办”查看。过去误归为待办的活动保留原记录，不自动把“明天”重新解释或重复保存为日程。

待办要参与自动学习排程：填写实际预计耗时→生成排程步骤草稿→校对确认，或者确认AI拆解；再点“规划未来7天”。预览列出固定课程/事项、可安排的学习块，以及缺信息或容量不足的原因，确认后时间块显示在课表。固定活动不需要通过任务拆解才能出现在日历。所有写入仍由用户确认。

```sh
cd frontend
CAMPUS_E2E_MODE=local CAMPUS_E2E_CALENDAR=1 npm run test:e2e -- calendar-todos.spec.ts
```

使用明确测试模型和隔离库，覆盖日程/待办/规划以及跨周定位；Windows设置对应环境变量。真实已配置供应商协议探针（收费、隔离库、不会确认写入学生任务或日程）：

```sh
uv run --project backend --no-sync python scripts/verify-chat.py --calendar
```

新工具白名单14项（新增create_calendar_event_draft/list_calendar_events），仍不开放shell、文件系统或通用浏览器；日程工具身份由后端注入，不接受owner_id。原始学校与跨系统验收边界不变。

## 删除待办与草稿（2026-10-15）

今日、课表及“待办 / 作业”的待办卡片可点击“删除待办”；确认弹窗显示标题和影响，点“取消”不写入。确认删除会同时清理该待办全部步骤、学习时间块（包括锁定及已完成记录），使关联拆解草稿和旧待确认计划失效，需重新规划。其他待办及其已保存安排不受影响。

所有未保存草稿（待办/作业、日程、课表、步骤拆解、七天计划，包括没有学习块的空计划）都有“删除草稿”。删除只丢弃预览；课表导入草稿同时取消对应导入，延迟的扩展捕获不能重新创建它。已保存内容请从对应待办删除，不能通过删除已确认草稿撤销保存。

删除前后刷新，核对待办、今日、课表、助手草稿列表同步；版本改变时应提示冲突，点击“刷新内容”，重新核对后才能再次确认。重复删除请求和服务重启都不能恢复已删除内容。历史聊天和确认回执保留；本功能不调用模型。

```sh
cd backend
.venv/bin/python -m pytest tests/test_deletion.py -q
cd ../frontend
CAMPUS_E2E_MODE=local npm run test:e2e -- deletion.spec.ts
```

浏览器场景使用独立临时数据库，请单独运行此命令；同一个本地测试服务的资料会跨浏览器上下文共享，不与其他会留下待办的 local 场景拼接运行。Windows PowerShell 使用 `$env:CAMPUS_E2E_MODE='local'` 后运行 `npm run test:e2e -- deletion.spec.ts`。原生 `scripts/verify-desktop.py` 也在独立目录创建并删除合成待办/草稿，重启后核对列表和幂等回执；不会操作本人的资料。

## 自然语言更新已保存待办的截止时间（2026-10-15）

助手中说“把阅读报告的截止时间改为明天晚上8点”。助手查询实时日期及原待办后，确认面板列出标题、版本、原/新截止和本人设置的时区；点“批准并执行”才更新原记录，不创建同名新任务。拒绝不更新；旧版本、已删除待办无法覆盖。缺日期或钟点会请本人补充，不默认23:59。明确说“补救截止时间”时保留原截止，设置补救日期；重新指定正式截止会清除旧补救日期，避免排程继续使用过期的补救时间。

已有步骤、锁定块和学习安排保留，不自动移动；旧待确认计划和关联拆解草稿失效，需重新生成。刷新待确认面板、批准后再次刷新或重启，核对截止与原待办ID一致，已完成的批准不能再次显示为待确认。

```sh
cd backend
.venv/bin/python -m pytest tests/test_task_deadline.py -q
cd ../frontend
CAMPUS_E2E_MODE=local CAMPUS_E2E_DEADLINE=1 npm run test:e2e -- deadline.spec.ts
```

模型/时钟 fixture 仅用于明确测试。真实已配置供应商验收（收费、临时隔离库，不操作本人任务）：从根目录运行 `uv run --project backend --no-sync python scripts/verify-deadline.py`。脚本创建合成已保存待办，发送普通中文，检查实际 get_current_time/list_tasks/set_task_deadline 工具调用、批准前不写入、批准后仅更新原记录。该功能加入时工具白名单15项（当前18项，见下文），新增写工具复用原服务端HITL授权、版本和幂等回执，不开放模型指定身份。


## 响应式草稿、连续保存与教学周日期（2026-10-15）

助手页面缩为紧凑工具栏；桌面宽屏左侧聊天、右侧校对，较窄窗口和手机改为上下排列。输入框铺满聊天区的剩余宽度，聊天记录独立滚动。无原图的任务草稿不再保留空图片栏，字段按卡片宽度切换单双列；截图草稿仅在容得下时左右并排。

在设置中确认学期第1周周一。例如2026-08-31，告诉助手“第14周之前完成C++大作业，11周之前完成agent大作业”。校对区应自动出现2026-11-30 00:00和2026-11-09 00:00（Asia/Shanghai），表示对应教学周开始前；显示首周日期和推算依据，不补23:59。旧版留下的同类草稿打开校对时也显示只读推算建议，正式保存前仍需本人确认。学期锚点变化会阻止旧推算直接保存，可再用对话修改原草稿。模糊的“明天”“第14周左右”“周末前”不会强行猜钟点。

继续说“把C++大作业草稿的截止改成明天晚上8点”，必须调用真实时间MCP、查询待确认草稿并更新原ID/版本；输入框日期应立即同步，刷新后仍是新日期，不新建同名草稿。逐份确认两份草稿，两条待办都应保存。独立作业/日程不受无关保存导致的全局版本递增影响；同一草稿被改、关联任务变化、旧计划或旧课表来源仍应拒绝覆盖。

当前实际工具白名单18项，新增list_assignment_drafts、set_assignment_draft_deadline、resolve_academic_deadline；不增加权限或通用文件/浏览器能力。草稿日期编辑复用校验、owner隔离、版本和持久幂等回执。

测试命令（每条Playwright命令使用各自新启动的隔离服务）：

```sh
cd backend
.venv/bin/python -m pytest tests/test_draft_usability.py -q
cd ../frontend
CAMPUS_E2E_MODE=local npm run test:e2e -- draft-layout.spec.ts
CAMPUS_E2E_MODE=local CAMPUS_E2E_ACADEMIC=1 npm run test:e2e -- academic-drafts.spec.ts
```

Windows PowerShell分别设置 `$env:CAMPUS_E2E_MODE='local'` 和 `$env:CAMPUS_E2E_ACADEMIC='1'` 后运行对应命令。测试模型只在tests.e2e_server明确环境开关下启用。真实模型验收（有调用费用、只用临时合成资料）：根目录 `uv run --project backend --no-sync python scripts/verify-academic-drafts.py`。脚本核对实际工具、两份草稿日期、对话修改原ID、确认前无任务及连续保存。


## 普通月日截止边界（2026-10-15）

说“11月1日之前完成报告”，应自动填入消息所在年份的11月1日00:00，表示当天开始前。界面注明补全年份的消息日期和时区，可直接校对保存，不必操作日期选择器。明确写2027年或明年会按原话计算；旧草稿也按其创建/消息日期提出只读建议，不按刷新日期改年份。截图缺少本人确认的消息日期时不自动补年份。仅“11月1日”“明天”无钟点/边界仍可通过自然语言补充，不默认23:59。

隔离测试：`CAMPUS_E2E_MODE=local npm run test:e2e -- calendar-deadline.spec.ts`（frontend目录）。真实配置模型探针：根目录 `uv run --project backend --no-sync python scripts/verify-academic-drafts.py --calendar-boundary`；有调用费用，只创建临时合成资料。

## 回到最新消息（2026-10-15）

消息足够长时上滑阅读历史，“↓ 回到最新消息”应悬浮在消息区底部，输入框上方，不必滚到底部才能看到。点击或键盘聚焦后按回车返回最新消息；空会话、手动滚到底部或返回成功后按钮隐藏。默认仍自动跟随最新回复，主动上滑阅读时遵循assistant-ui的原生滚动行为。

从frontend目录运行 `CAMPUS_E2E_MODE=local npm run test:e2e -- chat-scroll.spec.ts`。使用明确合成的长消息和现有测试模型、真实临时后端，覆盖390/1440px下按钮可见区域的坐标及直接点击（禁用测试工具自动滚动定位的帮助）、键盘、新会话与无横向溢出。

实现复用[assistant-ui Thread primitives](https://www.assistant-ui.com/docs/primitives/thread)的ViewportFooter和ScrollToBottom，补充sticky定位和disabled隐藏样式，没有新增滚动服务或模型权限。
