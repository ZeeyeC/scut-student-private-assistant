# 完整窗口还原与桌宠待办修改 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户已于2026-10-30明确要求“开始实现”；按已审阅v2及F09修订连续实施。

**Goal:** 严格还原用户接受的完整窗口参考，固定左导航、柔化色彩、浏览器优先导入，并让无顶部条的桌宠仅在单击后显示一个方形待办窗口。

**Architecture:** 保留AppKit/WKWebView/React/FastAPI架构与真实领域接口。App内容改为固定两列壳层与单独内容滚动；原生桌宠用一个NSPanel承载列表和详情，沿用任务查询、revision及幂等完成。设计参考、颜色和几何作为实现约束，并用同合成数据的截图对照验收。

**Tech Stack:** React/TypeScript/CSS、Swift/AppKit/WebKit、Vitest/Playwright、现有Python原生测试/发布工具；不新增UI框架或动画资源。

**Spec:** [v2完整设计规格](../specs/2026-10-30-ui-refinement-design.md)、[可点击参考](../../design/ui-redesign-v2/index.html)、[精确参数](../../design/ui-redesign-v2/visual-contract.json)、[参考截图](../../design/ui-redesign-v2/screens/)。基于当前源码`f39d822`；旧版2.5.0归档保留。

## Global Constraints

- 用户已授权开始实现；先修正F09并冻结已审阅参考。继续意见写入下表并同步原型/规格/基准，不能边开发边自行换造型。
- 正式产品只在独立App日常使用；浏览器仅在用户明确点击学校导入主按钮后打开。默认Chrome，记住Edge；无Safari或默认浏览器回退。
- 左导航始终留在左边，设置在底部；仅内容/详情正文滚动。宽度≥960为176、640–959为144、<640为56；不恢复底导航。
- 参考总图1280×820含38示意标题栏；正式产品内容区1280×782，原生外框按实际系统标题栏补足。颜色与几何以`visual-contract.json`及v2截图为唯一新准。不得以功能通过替代视觉验收，也不得自动更新设计截图迁就实现。
- 顶部条在所有桌宠状态移除，透明区域穿透；单击显示328×360、圆角12的单个待办窗口。原素材、地面锚点、时序、64MiB缓存与授权声明保留。
- 任务事实/草稿/校对/冲突/owner/revision/幂等保护不变；没有真实数据时不造数。模型发送同意只在实际方法内明确选择，不自动调用付费模型。
- 采用当前分支继续记录，正式实施前确认工作树及隔离方式；保留所有用户改动。执行与提交时持续更新[进度表](../../roadmap/Demo2.5-开发进度追踪表.md)及本计划。
- 下版暂定2.5.1；执行发布前核对未占用。更新VERSION/README/发布说明后独立构建，不覆盖2.5.0；不要求Demo2.2，不自动PR、公开发布或录屏。

## 用户意见记录（后续追加在同一处）

| 编号 | 用户意见 | 设计落实 / 实施任务 | 当前状态 |
| --- | --- | --- | --- |
| F01 | 第二种更好，但只在点击桌宠时出现 | 单个列表窗口；默认收起；Task4/5 | 已写入新参考，待用户继续反馈 |
| F02 | 最后效果严格与设计一样 | 固定参数、同数据截图、差异门槛、禁止擅自替换基准；Task1/2/6 | 已写入规格及验收 |
| F03 | 当前结果与最初设计差别大，复刻完整窗口 | 使用v1左栏/工作台比例，恢复完整App默认尺寸、移除额外切换按钮行；Task1/2 | 新完整窗口已出参考 |
| F04 | 导航不能跟其他部分上下滑动 | 根不滚，内容区独立滚动，宽窄均为左栏；Task1 | 原型滚动检查通过；产品未改 |
| F05 | 页面与桌宠均要视觉平衡 | 固定左右栏比例、对齐/留白、任务窗与角色光学间距；Task2/4 | 已写入参考及几何 |
| F06 | 色彩过渡生硬 | 接近的蓝灰色面、浅线、低饱和主色、无厚重背景块；Task1/2/4 | 新参数表已记录 |
| F07 | 浏览器导入默认，下面另两种方法 | 默认学校卡片，下方图片/PDF、文字折叠；Task3 | 新参考已演示 |
| F08 | 去掉桌宠上面的条，单击弹出方一点窗口 | draw/hitTest一起去条，列表/详情统一一个328×360面板；Task4/5 | 新参考已演示 |
| F09 | 今日安排中的竖线与课程标题重叠，实施时修复 | 时间、竖线、文字分列；竖线宽2点，与标题及次行文字净距至少12点；Task0/2 | 参考已RED→GREEN，净距12点；正式UI待Task2实现 |

## Review Focus

1. 长列表、长回复、原生窗口恢复旧560尺寸及跨断点缩放：导航不跟滚、不转底部，默认首次进入完整窗口（Task1/2）。
2. 导入面板反复展开、旧Edge偏好、缺浏览器/插件、关闭/取消：不自动开页、不自动识别，输入保留且原授权代次保护仍有效（Task3）。
3. 屏幕四角、负坐标、多缩放、可用区域不足：任务窗不挡角色、不超可用屏，原透明条区域穿透（Task4）。
4. 多任务/长标题、详情快速切换、旧请求延迟返回、重复完成、409/404/离线：选中对象正确、完成只一次，错误可恢复且关闭后不重弹（Task5）。
5. 原生全局监听误关内部点击、拖拽误触、提醒抢占、加载前导航：面板交互稳定，现有提醒/审批可达（Task4/5）。

---

### Task 0：参考准备与后续意见归并（D2）

**Files:** 本计划、规格、`docs/design/ui-redesign-v2/{index.html,visual-contract.json,README.md,verify-reference.mjs,preview-verification.json,screens/}`；进度表及材料索引。

**Interfaces:** v2原型只用合成数据；参数与截图是后续实现输入。`reference-manifest.json`记录原型/规格/参数/参考截图的SHA256及状态，不包含自身hash。

- [x] 核对v1完整窗口与当前正式代码，记录compact启动、顶部切换行、滚动层级、导入长表单、顶部条及任务环偏差。
- [x] 给出新的完整可点击窗口、导入默认层级、桌宠默认收起/单击列表/内部详情，保存精确参数。
- [x] 运行`node docs/design/ui-redesign-v2/verify-reference.mjs`：五页、滚动、导入、桌宠与320–1280宽检查；仅证明原型，不证明正式产品。
- [x] 一次独立可实施性复核；统一透明边导致的光学间距和原生标题栏尺寸，[处理记录](../../design/ui-redesign-v2/builder-check.md)保留依据。
- [x] 记录用户截图反馈F09：今日安排的装饰竖线压到标题。已核对参考CSS：通用button的padding重置覆盖条目文字缩进；旧检查只验证横向溢出，未覆盖这种内部重叠。
- [x] 冻结前修正F09参考：独立2点竖线列与文字列，净距至少12点；更新今日浅/深色截图与hash，并加入内部重叠检查。不能直接接受含此缺陷的旧截图。
- [ ] 用户继续反馈时逐项追加F10及以后条目；每项对应具体规格/实施任务，重新生成受影响截图与hash。
- [x] 用户以“开始实现”接受当前视觉，已将manifest状态从`proposal-awaiting-user-feedback`改为`accepted`，记录用户确认依据；正式开发开始前复核这三个输入，不能擅自替换基准。

### Task 1：完整窗口、左导航及共享外观（U3a）

**Files:** 修改`frontend/src/layout/AppShell.tsx`、`frontend/src/style.css`、`frontend/src/App.tsx`、`campus-pet/Sources/AppDelegate.swift`、`campus-pet/Resources/Bridge.js`；新增`frontend/src/layout/workspace-tokens.css`、`campus-pet/Sources/WorkspaceAppearance.swift`、`frontend/e2e/ui-refinement.spec.ts`；更新`campus-pet/tests/NativeTests.swift`。

**Interfaces:** 复用`AppShell`及`NavigationTarget`，不新建路由器。新增Swift `WorkspaceWindowLayout.initialFrame(visibleFrame: NSRect, chromeInsets: NSEdgeInsets) -> NSRect`：以1280×782产品内容加实际系统chrome后居中，按可用屏幕内缩后裁限；`chromeInsets`从当前NSWindow外框与内容区差值取得，不写死标题栏高度。`WorkspaceAppearance`提供JSON中相同浅/深色和面板尺寸；前端tokens同名语义，不再零散写替代色。

- [x] 写行为失败用例`sidebar_stays_left_while_content_scrolls`：≥20任务或长回复产生内容滚动；滚前后导航及底部设置的y/height偏差≤0.5；`document.scrollingElement.scrollTop===0`；跨1280→768→560→1280后仍在左边，内容能看到最后一项。
- [x] 写原生失败用例`workspace_initial_frame_is_full_and_clamped`：可用屏1440×900且系统顶部chrome=28、其他=0时得到1280×810外框及1280×782产品区；chrome=38时得到1280×820。小屏/负原点不超`visibleFrame`；首次启动不因旧compact值回到560。使用新的`CampusPetWorkspaceV2`窗口恢复键保留旧设置，新键有合法用户尺寸则恢复并按可用屏裁限。
- [x] Run `npm --prefix frontend run test:e2e -- ui-refinement.spec.ts`及`backend/.venv/bin/python campus-pet/tests/run_native_tests.py`，保留本任务断言失败证据。
- [x] 以网格固定侧栏，根满高不滚、main独立滚；清理冲突的旧shell/强制compact/底导航覆盖。按JSON落地字体、颜色和176/144/56侧栏；小宽度保留可访问名称与设置图标。
- [x] 原生默认完整窗口；移除内容顶部“主窗口”按钮行，让WK内容接原生内容布局。尺寸切换若保留则放菜单，不另占页面高度。Bridge不在启动硬设compact；初始化和resize以实际可用宽度通知布局，不改变左栏规则。
- [x] 同命令通过，补`npm --prefix frontend run typecheck`；截图对照导航和内容起点，更新D2/U3证据并提交本任务。

### Task 2：逐页还原与视觉平衡（U3b）

**Files:** 修改`frontend/src/Today.tsx`、`Calendar.tsx`、`TasksPage.tsx`、`Chat.tsx`、`Settings.tsx`、`layout/DetailPanel.tsx`及`style.css`；新增`frontend/e2e/ui-refinement.visual.spec.ts`、`scripts/verify-ui-reference.py`、`docs/validation/demo2.5.1/visual/`。

**Interfaces:** 保留原组件props/API、`DetailPanel({open,title,onClose,children,footer})`。`verify-ui-reference.py --reference <design-dir> --actual <validation-dir>`读取明确区域的参考/实现截图与尺寸JSON，输出各图像素比例、几何差异；不更新任何参考文件。

- [x] 固定合成数据，先写视觉失败用例`workspace_matches_accepted_reference`覆盖今日、日程、任务、任务详情、助手、设置，记录真实差异。参考截图裁取`(0,38,1280,782)`，实际取同尺寸WK产品区，不缩放或让系统标题栏造成底部误差。数据名称、时间、数量、字体、逻辑尺寸和系统外观与原型一致；固定日期为2026-10-30，仅测试环境生效。
- [x] Run `npm --prefix frontend run test:e2e -- ui-refinement.visual.spec.ts`，确认当前正式UI与基准差异为RED；不把现有UI截图另存成预期图。
- [x] 按参考实现接下来/其他待办/右侧安排；≥1200右栏280/间距43，960–1199为236/32，<960移到下方。表格/列表、周日历、对话、五组设置分别保留原稿的留白和层次，功能在原详情中可达。
- [x] F09失败用例`agenda_marker_never_overlaps_text`：每条安排的竖线右边与标题/地点/时段/时长文字左边净距≥12点；标题和次行同列对齐。覆盖1280/1024/960/768/560/390/320宽、80字标题及125%/200%文字放大；允许换行，不能以缩小文字或隐藏竖线/正文通过检查。实现使用独立布局列，并防止通用按钮reset覆盖条目间距。
- [x] 详情宽448并限定在内容区内，头尾固定、正文独滚；保留现有多层面板inert/Esc/输入保留，不引入导航区域被覆盖或根被`scrollIntoView`拖动的问题。
- [x] 加入`long_titles_and_nested_panels_keep_balance`：80字中英任务名、20行要求、长助手回复、宽窄切换、多个详情交错打开关闭；无遮挡、无横溢出、输入不丢，键盘可到关闭和确认。
- [x] 同命令GREEN；运行`python3 scripts/verify-ui-reference.py --reference docs/design/ui-redesign-v2 --actual docs/validation/demo2.5.1/visual`，几何≤2点、同数据超阈像素≤1%，颜色一致；逐页人工看左右重心，记录证据并提交。

### Task 3：浏览器优先的单一导入面板（U3c）

**Files:** 新增`frontend/src/TimetableImportPanel.tsx`；修改`Calendar.tsx`、`SchoolImportPanel.tsx`、`TimetableRecognition.tsx`及相关样式；更新`frontend/e2e/app-school-import.spec.ts`、新增`frontend/e2e/timetable-import-layout.spec.ts`。

**Interfaces:** `TimetableImportPanel({open,onClose}: {open:boolean;onClose:()=>void})`持有`method: 'school'|'image'|'text'`展示状态，默认school。学校流程复用现有`nativeImport`、`ImportBrowserSettings`和`campus-start-import`，将`SchoolImportPanel`中的流程内容提取为`SchoolImportContent`以嵌入同一面板；全局事件打开同一入口，避免新旧面板叠两层。校对仍使用`DraftReview`/识别校对，手工课程编辑原接口保留。

- [ ] 写失败用例`browser_is_primary_without_side_effect`：初开学校卡片可见、图片/PDF和文字折叠；拦截native开页及识别POST并断言0次；只有点主按钮才一次打开。已有Edge偏好正确显示。
- [ ] 写`secondary_methods_preserve_input_and_do_not_launch_browser`：展开文件/文字输入、切换/关闭重开仍保留；未同意识别不能POST；显式提交才创建原任务；两方式不唤浏览器；手工单门课程入口仍可达。
- [ ] Run `npm --prefix frontend run test:e2e -- timetable-import-layout.spec.ts app-school-import.spec.ts`，确认新增断言RED。
- [ ] 按默认导入截图实现主卡片+下方两行；只在展开方法内显示其限制/同意/错误/进度。扩展安装指引放底部折叠；完成后仍在App校对/冲突确认，不在关闭面板时擅自取消有效导入。
- [ ] 缺浏览器/插件、5秒握手失败、取消/过期/重试、重复回传用现有链路回归；样式调整不能改变grant、owner、bindingGeneration与收据语义。真实学校本人往返仍单列待验收。
- [ ] 同命令GREEN；默认与展开状态截图对照参考，更新进度后提交。

### Task 4：单个原生方形面板与无条角色（N5a）

**Files:** 新增`campus-pet/Sources/PetTodoPanel.swift`、`PetTodoLayout.swift`、`campus-pet/tests/PetTodoPanelTests.swift`；修改`PetView.swift`、`PetBubbles.swift`、`PetTask.swift`、`AppDelegate.swift`、`tests/NativeTests.swift`、`tests/run_native_tests.py`、`Sources/SmokeTest.swift`。

**Interfaces:** `PetTodoLayout.frame(near characterRect: NSRect, within visibleFrame: NSRect, preferredSide: Side) -> NSRect`返回328×360或可用屏裁限后的框，按左右/上下候选选择、内缩12、视觉间距32，不改角色位置。`PetTodoPanel: NSPanel`提供`render(_ state: PetTodoPanelState)`和关闭/选中/完成/全部任务回调；状态为loading、list、detail、error，列表和详情共用同一窗口。新增测试文件注册进现有runner，不增加第二个@main。

- [ ] 写`pet_todo_geometry_is_visible_without_covering_character`：四角、负坐标、420×560原图的透明边、0.75/1/1.5倍角色、空间不足、屏幕切换，框在可用区域且不盖可见角色；多个候选可用时位置稳定。
- [ ] 写`pet_has_no_top_strip_and_old_area_clicks_through`：7业务状态/提醒/动作均无文字条，旧条仅透明像素区域`isInteractive==false`，角色实际不透明像素仍命中；拖拽4点阈值不变。
- [ ] Run `backend/.venv/bin/python campus-pet/tests/run_native_tests.py`，确认RED；随后实现原生布局/结构化视图和与JSON一致的外观，移除`drawBubble`及其旧命中区域，而非仅隐藏文字。
- [ ] 使用一个非激活NSPanel，65头部/49底部/58任务行/18边距/12圆角；列表正文滚动，加载/空态/失败在正文，取消独立圆球窗和旧奶黄文本窗呈现。保持现有透明PNG、状态机、动作、缓存与署名。
- [ ] 写实际App烟测：单击角色开/关，默认不显示，Esc/外点关闭，内部滚动/勾选不误关，拖动只移动并收面板，右键仍菜单；隐藏/退出清理监听器和面板。原生烟测必须检查实际NSPanel，不只测坐标算法。
- [ ] 同测试GREEN，实际App固定源帧截图与pet-idle/pet-todos/pet-detail对照；分别记录真实单屏与模拟多屏结果后提交。

### Task 5：真实待办、完成、详情与精确导航（N5b）

**Files:** 修改`PetBubbles.swift`（迁移控制逻辑）、`TaskDetails.swift`、`PetTodoPanel.swift`、`AppDelegate.swift`、`Resources/Bridge.js`、`frontend/src/layout/navigation.ts`及相关原生/桥接测试；新增需要的`PetTodoState.swift`，不保留第二份事实存储。

**Interfaces:** 数据筛选继续用`PetScheduledTask.today(tasks:blocks:timezone:now:)`；新控制器只管理选中ID、请求代次、pending完成和面板展开。新增`AppDelegate.showTaskInAssistant(id: String)`发送序列化的`{page:'tasks',taskId:id}`；Bridge `navigate(target)`接受旧字符串或严格验证后的任务目标，WK尚未就绪时保存最近一个有效目标，ready后只投递该目标。详情和完成继续使用现有真实接口。

- [ ] 写失败用例`todo_stale_results_never_replace_selection`：A→B快速切换、关闭后旧详情返回、展开后刷新、任务被删除；窗口不重弹、B不显示A、404给刷新入口。
- [ ] 写`todo_completion_is_revision_checked_and_single_flight`：连击只请求一次、请求中禁用、成功保留划线并减数量、409/离线回滚且可重试、重新展开以服务端为准；保留幂等键与原revision，不把前端示例状态代码搬进正式程序。
- [ ] 写`pet_task_navigation_keeps_id_before_web_ready`及桥接测试：旧字符串兼容、合法taskId精确打开、恶意/空ID拒绝、加载前目标在ready后送达、跨页重复选择仍定位。Run `npm --prefix frontend test -- navigation pet-bridge`及原生runner，确认RED。
- [ ] 迁移原查询/完成/详情控制到同一面板；旧代次返回丢弃。勾选显式完成整个任务、右键不再完成；无完成重开接口时不显示虚假“重新打开”。在App中查看要定位所选任务而非仅进任务列表。
- [ ] 将无顶部条后的提醒/审批入口接到面板内的按需待确认操作；原系统提醒不丢，提醒不自动展开面板、不重建顶部条。测试外部点击监视器将pet和todoPanel视为内部，VoiceOver按压与单击语义相同。
- [ ] 同测试GREEN；`backend/.venv/bin/python campus-pet/verify.py --app <本轮新构建App>`实际验证数据流、透明点击、请求错误恢复及精确跳转，记录后提交。

### Task 6：最终视觉对照、全量回归与2.5.1发布（V2/R2）

**Files:** 更新本计划/追踪表、`README.md`、`campus-pet/README.md`、`campus-pet/VERSION`、`docs/releases/Demo2.5.1.md`、`docs/validation/demo2.5.1/`；仅在确需新视觉/原生门禁时调整`verify.py`和`scripts/release-macos.py`。

**Interfaces:** 参考manifest锁定v2设计；实际验证目录和发布包引用其hash。发布继续使用现有脚本，新增版本不复用/复制旧App。

- [ ] 审核Task1–5的视觉截图：六页/详情、默认导入、桌宠收起/列表/详情，含1280与窄窗口；逐项核对F01–F08及后续意见。未通过就继续修复，不给“基本相同”结论。
- [ ] Run前端测试/类型/构建、扩展测试/类型/构建、后端/脚本pytest、全量Playwright、原生逻辑/HTTP/真实App及素材冻结门禁；前端先build。扩展构建保留项目规定的PUBLIC_ORIGIN与SCUT_ADAPTER_PATH，不让构建配置退回null。
- [ ] 按现有执行工作流做最终独立代码检查；发现实质问题先复现再修复。设计原型通过、正式UI通过、原生实机通过及真实外部验收分开记录。
- [ ] 确认2.5.1未占用，更新VERSION/README/本版说明后运行`backend/.venv/bin/python scripts/release-macos.py --version 2.5.1`。生成App、App ZIP、当前工作树源码ZIP、说明、验证结果、manifest及SHA256；所有门禁通过才清理明确缓存。
- [ ] 核对哈希/签名/ZIP/无Key及个人资料、完整保留素材声明。旧2.5.0、源码、依赖、配置、data/backups与原任务书保留；实际学校/OCR/多物理显示器等未做的验收继续如实保留。
- [ ] 更新工作区README最新入口、进度和提交记录；GitHub同步遵循用户已有授权范围，不创建PR或公开App release。最终报告附设计与实际对照及真实剩余项。

## 计划自查

F01/F08→Task4/5，F02→Task0/2/6，F03/F04→Task1/2，F05/F06→Task1/2/4，F07→Task3，F09→Task0/2。五类Review Focus均有对应失败用例。旧网页入口不恢复，旧审批/校对/任务完成的保护不删。新计划与旧总计划、桌宠计划通过进度表关联；旧版已完成项不被改写成新版完成。
