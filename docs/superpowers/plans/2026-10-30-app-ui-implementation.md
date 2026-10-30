# 独立App新界面与桌宠 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task。用户本轮要求把NaiWa形象替换加入计划，尚未要求执行本计划；正式实施前采用已确认的视觉稿。

**Goal:** 将简洁工作台落地为独立App唯一日常界面，仅学校导入打开浏览器，并使用NaiWaChatPet角色素材替换现有桌宠。

**Architecture:** 保留现有React业务组件、FastAPI事实/草稿/确认、Swift/AppKit和WKWebView；重组页面与详情，不另造任务/规划存储。学校导入使用受限外部浏览器会话回传，角色资源通过独立资产包接入原桌宠状态。

**Tech Stack:** React/TypeScript、React Query、FastAPI/SQLite、Swift/AppKit/WebKit、pytest/Vitest/Playwright。

**Spec:** [App界面设计](../specs/2026-10-30-ui-redesign-design.md)、[NaiWa形象设计](../specs/2026-10-30-naiwa-pet-assets-design.md)、[可点击原型](../../design/ui-redesign-v1/index.html)。

## Global Constraints

- 日常使用只在App内；浏览器仅由明确的学校课表导入操作打开。图片/PDF/文字导入、校对及保存留在App。
- 四个主入口为今日、日程、任务、助手；设置位于底部。目标与复盘归入任务，复杂操作放详情面板，移除装饰文字和重复入口。
- 保持原接口、owner、版本、幂等收据和明确确认；未知、0、估算、实际分开。课程/锁定计划不自动移动。
- NaiWa固定来源及授权、原比例、原时序、64MiB帧缓存等约束以独立形象计划为准；新包全程同一角色。
- 暂定交付版Demo2.5（2.5.0）；实施前核对未占用，从当前源码独立构建，不覆盖2.4.9或其他归档。配置、data/backups、依赖、源码与任务书保留。
- 不自动付费模型测试、PR、推送、公开上传或录屏。当前5349是设计预览，不作为产品入口。

## Review Focus

- 改导航后桌宠/提醒/审批事件找错页面或遗失目标线程（Task1）。
- 表单收进详情后，未确认/冲突/过期数据被一键静默保存（Task2）。
- WKWebView与Chrome会话不共享，导入不能靠旧网页版Cookie或任意网页消息认证（Task3）。
- 学习链接、`window.open`、默认启动器或旧菜单仍无意唤出浏览器（Task3）。
- 新PNG比例/时序与旧播放器不兼容，正式包暗中使用旧形象回退（Task4）。

### Task 1：App壳层与四项导航

**Files:** 创建 `frontend/src/layout/AppShell.tsx`、`frontend/src/layout/navigation.ts`、`frontend/src/layout/navigation.test.ts`；修改 `frontend/src/App.tsx`、`style.css`、`campus-pet/Resources/Bridge.js`、`campus-pet/Sources/AppDelegate.swift`。

**Interfaces:** `PageId = 'today'|'calendar'|'tasks'|'assistant'|'settings'`；导航目标 `{page, taskId?, focusDate?, calendarFilter?, taskTab?, threadId?}`；保留并归一现有 `campus-navigate`、`campus-calendar-saved`、`campus-timetable-focus`、`campus-pet-review` 事件。目标/复盘旧入口映射到tasks子页，提醒打开calendar具体日期，审批定位assistant具体线程。

- [ ] 写Vitest失败用例：旧事件正确映射新页面、待确认线程/任务ID保留、重复定位仍可生效、非法目标拒绝。
- [ ] Run `npm --prefix frontend test -- navigation`，确认RED。
- [ ] 实现主窗口左导航与快捷面板底导航，设置固定底部；共用真实查询缓存。仅重组壳层，不移除业务组件。
- [ ] 同命令GREEN；原型确认的尺寸与字体落到应用样式，补320/390px与实际Mac快捷面板检查，再提交。

### Task 2：页面整合与统一详情

**Files:** 创建 `frontend/src/layout/DetailPanel.tsx`、`frontend/src/TasksPage.tsx`、`frontend/src/ReviewInbox.tsx`、`frontend/e2e/app-workspace.spec.ts`；修改 `Today.tsx`、`Calendar.tsx`、`Chat.tsx`、`Settings.tsx`及相关领域组件的承载方式。

**Interfaces:** `DetailPanel`接收 `{open,title,onClose,children,footer}`，不自行发起保存；`TasksPage`承载待办/目标/复盘；`ReviewInbox`聚合原草稿/变化/时长建议并回到各自确认器，保留原ID与版本。原确认服务继续负责校验和收据。

- [ ] 写浏览器RED：导航到任务/目标/复盘；详情开关保留未保存输入；安排先预览后确认；冲突需明确核对、来源变动409可恢复；计时记录不自动完成任务。
- [ ] 加入显示检查：不再铺出重复介绍、默认长表单和多组同义保存按钮；未知实际显示未记录，明确0仍显示0。
- [ ] 实现今日少量待办与安排；日程共享课程/学习筛选；任务子页承载目标复盘；设置改五组摘要，资源类型放详情；助手写入复用原批准流程。
- [ ] Run `npm --prefix frontend test`、`npm --prefix frontend run typecheck`及新增浏览器用例，确认GREEN并提交。保留原业务断言，只调整过时选择器和展示文案。

### Task 3：学校导入专用浏览器通道

**Files:** 创建 `campus-pet/Sources/BrowserLaunchPolicy.swift`、`frontend/src/SchoolImportPanel.tsx`、`backend/app/desktop_import_bridge.py`、`backend/tests/test_desktop_import_bridge.py`、`frontend/e2e/app-school-import.spec.ts`；修改 `AppDelegate.swift`、`ServiceController.swift`、`backend/app/browser_imports.py`、`frontend/src/BrowserImport.tsx`、`ImportGuide.tsx`、`extension/entrypoints/app.content.ts`、`extension/entrypoints/background.ts`、`extension/lib/protocol.ts`、`backend/app/main.py`、启动文档和相关测试。

**Interfaces:** `BrowserLaunchPolicy`仅接受已由App创建且未取消/过期的学校导入上下文；URL限已核实学校配置/受限扩展桥接。复用现有 `/browser-imports` 状态与草稿确认；扩展回传绑定owner、导入任务、有效期及一次性授权，不共享WKWebView/Chrome Cookie假设。

- [ ] 实现边界已确定：在App已认证会话里为原导入资源签发短期grant；外部最小桥接页URL只在fragment携带随机令牌，加载后清除fragment。服务端仅存令牌hash，绑定owner/import ID，过期不晚于原15分钟会话。grant只能读取该导入状态和提交事件/捕获，不可读写任务、模型配置或其他资源。
- [ ] grant捕获成功后消费；同操作ID与同捕获内容可返回原收据，不同内容/跨导入重放拒绝；App取消立即使grant失效。最小桥接页继续通过现有content script/后台扩展向学校页面发起采集，回传后App轮询原导入状态，不读取学校密码或借用浏览器的助手登录Cookie。
- [ ] 写RED：启动/导航/聊天/设置/提醒不唤浏览器；任意URL、伪造消息、跨owner、过期/取消会话被拒绝；只有用户点学校导入才允许一次发起。
- [ ] 写RED：Chrome学校采集→回到App校对→确认后保存；重复回传不重复导入；拒绝/取消不保存。图片/PDF/文字全程不触发外部浏览器。
- [ ] 移除旧完整网页版菜单、常驻浏览器链接和默认自动打开网页；外部HTTP导航和新窗口统一进入策略。需要技术桥接时只提供受限回传，不提供完整助手网页。
- [ ] 新用例GREEN；在实际App与Chrome/Edge验证首次扩展安装、本人登录、取消/过期/重试。合成测试与真实学校登录验收分开记录，再提交。

### Task 4：NaiWa桌宠形象替换

**Files/Interfaces:** 按 [NaiWa形象替换详细计划](2026-10-30-naiwa-pet-assets-implementation.md) 四项执行，向总计划交付已核实素材包、Swift播放器、状态/几何交互、来源声明与实际Mac验收。

- [ ] 完成固定来源/授权、选材预览与可审计导入。
- [ ] 完成非方形画布、原时序、入/出场、按需缓存与统一坐标。
- [ ] 完成7种状态、提醒、动作菜单、拖拽/点击/任务环及同来源回退。
- [ ] 完成图标/构建资源/声明及实际Mac验证；授权或画面验收缺失时不把本任务记为完成。

### Task 5：统一回归、独立复核与发布

**Files:** 更新 `frontend/playwright.pet.config.ts`、`campus-pet/Sources/SmokeTest.swift`、`scripts/release-macos.py`、`campus-pet/VERSION`、`README.md`、`docs/releases/Demo2.5.md`及本版验证材料。

- [ ] 新前端先build，再跑会读取静态资源的全量后端和浏览器。保持原规划/执行/目标/计时/批量校历等功能回归；增加App专用导入与新素材冻结检查。
- [ ] Run 后端/脚本pytest、前端/扩展测试与类型/构建、Playwright、原生逻辑、健康HTTP、实际App和冻结后台检查。开发者浏览器测试用于内部前端验证，不恢复网页版产品入口。
- [ ] 完成后做一次全分支独立只读复核；重要问题先复现RED再修复并回归，不用截图或上游release_gate替代实际App验收。
- [ ] 更新VERSION/说明/README后运行 `backend/.venv/bin/python scripts/release-macos.py --version 2.5.0`；产出App、应用ZIP、当前工作树源码ZIP、说明、验证结果、manifest及SHA256。
- [ ] 校验授权声明、无旧角色混入、无Key/个人资料、ZIP与签名、浏览器仅学校导入会唤出。通过后清理明确缓存；保留旧正式包和失败证据。

本文件已进行来源、路径与接口自检；所有复选框表示未来实现工作，不表示本轮已修改正式App。
