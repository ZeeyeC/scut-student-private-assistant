# NaiWaChatPet 形象替换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. 每项按RED→GREEN、必要回归、本地提交完成；仅在开始实施时执行，本次请求只更新计划。

**Goal:** 使用用户指定仓库的角色素材替换现有Mac桌宠，保持现有任务、提醒、审批和原生交互。

**Architecture:** 上游固定提交→明确素材清单与授权记录→本地资源导入→Swift清单/按需帧缓存→现有PetMood、绘制与交互。资源与动作元数据统一，不迁入上游业务运行时。

**Tech Stack:** Python3.12资源导入/校验、Swift/AppKit、透明PNG、既有原生测试与release-macos流程。

**Spec:** [NaiWa形象设计](../specs/2026-10-30-naiwa-pet-assets-design.md)、[独立App界面设计](../specs/2026-10-30-ui-redesign-design.md)。

**Execution records:** 与[总计划](2026-10-30-app-ui-implementation.md)共用`codex/demo2.5-app-ui-naiwa`和[进度追踪表](../../roadmap/Demo2.5-开发进度追踪表.md)；本计划Task1–4分别对应追踪项N1–N4。原任务书、已归档调研与待补素材见[实施材料](../../materials/demo2.5/README.md)。

## 2.5.0后交互修订

本计划的素材/播放器与N1–N4结果保留；用户最新要求以[新修改计划Task4/5](2026-10-30-ui-refinement-implementation.md)和[v2桌宠规格](../specs/2026-10-30-ui-refinement-design.md)为准，替代下文历史任务环/顶部条呈现要求。

- [x] 新参考记录：去常驻顶部条，单击展开一个方形待办窗，列表和详情内部切换。
- [ ] 正式原生实现去条/透明穿透、单面板、真实任务与提醒接线。
- [ ] 按新参考截图对照和真实App验收，不用旧任务环测试作为新面板完成依据。

## Global Constraints

- 固定上游提交 `008eb12636f517aedecee6f1a1fc773c2f0df6c4`；角色授权依据明确后才纳入正式包，保留适用许可和署名。
- 素材原始比例420×560；使用声明的fps或单帧ns，不沿用320×320/20fps假设。单帧姿态保持静态语义。
- 帧缓存64MiB上限，仅按需解码；新待机帧作为统一回退，不混入旧生成角色或视频动作。
- 只在学校课表导入流程唤出浏览器；素材来源在App内显示/复制。新版本独立构建，无历史基线要求。
- 保留任务环、审批、提醒、拖拽、暂停、隐藏与减少动态效果。保留旧正式包、个人资料、配置和依赖。

## Review Focus

- 元数据与真实PNG尺寸/哈希不符、路径逃逸或半导入：拒绝并保留已有资源包（Task1）。
- 非方形角色、不同基线/透明边界：绘制、点选和拖拽使用同一变换（Task2/3）。
- 24fps片段、85ms待机、静态一帧与入/出场：不得统一20fps或错误重播（Task2）。
- 动作播放中真实状态变化、提醒/隐藏/休息：优先业务状态并停掉无用解码（Task3）。
- 仅换默认帧、图标/回退仍用旧角色，或打包漏文件：冻结资源检查必须发现（Task4）。

### Task 1：固定来源、资源选择和可审计导入

**Files:** 创建 `campus-pet/art/naiwa/SOURCES.md`、`campus-pet/art/naiwa/selected-assets.json`、`scripts/import-naiwa-assets.py`、`scripts/tests/test_import_naiwa_assets.py`；输出到 `campus-pet/Resources/NaiWa/`。

**Interfaces:** CLI `import-naiwa-assets.py --source <只读上游检出> --selection <清单> --output <资源目录>`；输出 `asset-pack.json`，含schema_version、upstream_ref、源路径/SHA256、canvas、default_frame、clips（frames/duration_ns/loop/transitions）、states及资源授权记录。fps归一为每帧`round(1_000_000_000/fps)`纳秒，原fps另存来源；单帧手动姿态单独使用`pose_hold_ms=800`，不重复解码或篡改其源fps。

- [x] 选材固定为基础idle28帧、状态用greet/ponder/focused/curious/worried/sleepy、手动smile及surprised三段、原icons/icon-256.png。记录各自授权依据；读取原始PNG并制作静态/逐帧预览，确认不是错误目录、占位图或不相符姿态。原始记录与既有素材分开。
- [x] 写失败测试：篡改SHA、420×560声明对应错误尺寸、缺帧、非法路径/符号链接、无效帧时长、未知来源版本、失败导入后原资源包保持原样。
- [x] Run `PYTHONPATH=backend backend/.venv/bin/python -m pytest scripts/tests/test_import_naiwa_assets.py -q`，确认RED。
- [x] 实现原字节校验、受限路径、明确字段和暂存后原子替换；只复制选中PNG与必要声明，输出同来源默认帧。基线待机按28帧×85,000,000ns；表情按各自清单。
- [x] 同命令GREEN；检查清单的帧/文件/来源一一对应，再本地提交。授权未明确时继续做UI/合成测试，不把未明确素材放入发布包。

### Task 2：元数据播放器、按需缓存和公共坐标

**Files:** 创建 `campus-pet/Sources/PetAssetPack.swift`、`PetFrameCache.swift`、`PetGeometry.swift`、`campus-pet/tests/PetAssetTests.swift`；修改 `PetAnimation.swift`、`campus-pet/tests/NativeTests.swift`、`campus-pet/tests/run_native_tests.py` 的测试入口注册。

**Interfaces:** `PetAssetPack.load(from: URL) throws -> PetAssetPack`；`clip(for: PetMood) -> PetClipSpec`；`PetClipSpec.frameIndex(at: TimeInterval) -> Int`；`PetFrameCache.frame(clip: PetClipSpec, index: Int) -> NSImage?`；`PetGeometry(sourceSize: NSSize, groundY: CGFloat, targetRect: NSRect)`提供 `sourcePoint(fromView: NSPoint) -> NSPoint?` 与 `viewRect(fromSource: NSRect) -> NSRect` 转换。缓存构造参数 `byteLimit` 默认64×1024×1024。

- [x] 写失败测试：85ms跨帧、24fps、静态单帧、循环与末帧、不同片段切换重置索引、缺转场与坏资源回退；420×560等比缩放不裁头脚；缓存计费/淘汰不超过上限。
- [x] Run `backend/.venv/bin/python campus-pet/tests/run_native_tests.py`，确认RED。
- [x] 按源清单加载与验证；clip持有元数据而非整套解码图数组，帧缓存按需加载并受限。透明像素与显示图复用相同帧字节，避免哈希验证后再从可变路径读取另一份图。
- [x] 相同命令GREEN，覆盖原有原生逻辑，再提交；本任务产物可使用合成PNG验证，不依赖未明确授权素材。

### Task 3：状态、点击区域、提醒和动作菜单接入

**Files:** 修改 `campus-pet/Sources/PetView.swift`、`PetAnimation.swift`、`AppDelegate.swift`、`PetBubbles.swift`、`ScheduleReminder.swift`、`campus-pet/tests/NativeTests.swift`、`PetAssetTests.swift`。

**Interfaces:** 继续消费 `PetMood` 与 `receiveAssistantMood`，新资产状态表按设计映射；`isInteractive`、`isReminderBelly`和绘制均使用Task2 `PetGeometry`。动作菜单来自已验证clip，显示名对应真实素材。

- [x] 写失败测试：7种业务状态均选择新角色；提醒/待批准打断随机表演、结束回当前状态；透明边缘不吞鼠标；提醒区域只在实际新角色可点击区域内。
- [x] 补失败测试：隐藏、休息和减少动态效果停止不必要解码；拖拽/缩放后基线不跳；错误资源用新默认帧回退；连续切换不残留旧角色或旧动作名称。
- [x] 原生逻辑RED后接入状态表与共享几何；提醒使用原图上的轻量标记，保留提醒点击功能，替换旧整图HSV染色假设。
- [x] 原生逻辑GREEN；检查任务环、打开主窗口/快捷面板、状态审批及暂停恢复，再提交。

### Task 4：图标、构建资源与实际Mac验收

**Files:** 修改 `campus-pet/build.py`、`campus-pet/Sources/SmokeTest.swift`、`campus-pet/README.md`；创建 `scripts/verify-pet-asset-pack.py`、`frontend/src/SettingsAbout.tsx`；修改 `frontend/src/Settings.tsx` 与 `scripts/release-macos.py`。

**Interfaces:** `verify-pet-asset-pack.py --app <当前新App>` 检查包内资源、哈希、默认帧、全部可达clip和声明；关于面板只显示本机声明与可复制来源，任何来源控件不触发浏览器。

- [x] 写资源冻结检查RED：漏帧、旧角色回退、旧三视频动作菜单、缺署名、旧320尺寸或20fps硬编码均能发现；旧“3个视频动作”断言改为已验证包中的真实动作语义，不删业务检查。
- [x] 调整构建：复制选中NaiWa包、同来源图标/默认帧与适用声明；旧资源不再进入新App。关于面板提供本地声明。
- [x] 新源码App里逐状态拍照/播放核对；检查黑白底无色边、透明点击、拖拽、任务环、提醒、隐藏/唤醒、缩放；记录缓存与播放CPU。多物理显示器未实测就明确保留为待验收。
- [x] 运行原生逻辑、HTTP健康10场景、实际App smoke、资源包校验；将证据交给总计划最终发布步骤。发布失败保留旧包与暂存，不能把资源清单通过代替本机实际播放验收。

## 交付

新角色素材清单/许可来源、状态映射、可复现导入工具、原生资源与交互测试、实际App画面及性能记录，随新UI统一进入后续版本。实现与验收状态随[进度表](../../roadmap/Demo2.5-开发进度追踪表.md)更新，真实外部样本不以本轮归档替代。

## 2.5.1 交互与视觉修订

原素材来源、时序、状态机与64MiB缓存保持；后续按[新修订计划Task4/5](2026-10-30-ui-refinement-implementation.md)替换呈现。上方任务环/提醒肚皮是2.5.0的历史记录。

- [x] 所有状态去顶部条与旧命中区；单击只开一个328×360列表/详情窗口。
- [x] 单窗口真实完成、错误恢复、精确App定位、提醒入口及三态视觉门槛通过。
- [ ] 新App独立构建、原生及素材冻结检查，随2.5.1归档。
