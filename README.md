# 课间 · 华工学生助手

最新发布 **2.6.0 可确认的个人记忆**，分支 `codex/personal-agent-memory`。[本版说明](docs/releases/Demo2.6.md) · [实施计划](docs/superpowers/plans/2026-11-01-personal-memory-implementation.md) · [验证记录](docs/validation/demo2.6/README.md)。本地偏好需确认后才召回，支持期限、修改、遗忘及关闭召回；设置 → 学习偏好 → 记忆与偏好。17项发布门禁、733后端+20子项、109前端、95界面、正式包原生记忆确认、35哈希及双ZIP检查通过，原资料身份已恢复。[打开App](/Users/czy/ProjectManagement/Demo2.6/课间桌宠.app) · [安装包](/Users/czy/ProjectManagement/Demo2.6/Demo2.6-Mac-AppleSilicon.zip)。行为学习与真实模型自由表达评测仍留后续。

历史发布 **2.5.7 聊天作业截图闭环**：[说明](docs/releases/Demo2.5.7.md) · [验收](docs/validation/demo2.5.7/README.md)。17项发布检查通过，支持附件菜单、单图选择/拖入/粘贴、校对修改与确认保存。[打开App](/Users/czy/ProjectManagement/Demo2.5.7/课间桌宠.app) · [安装包](/Users/czy/ProjectManagement/Demo2.5.7/Demo2.5.7-Mac-AppleSilicon.zip)。

当前更新 **2.5.4 校区节次快捷选择**：[说明](docs/releases/Demo2.5.4.md) · [验证](docs/validation/demo2.5.4/README.md)。课表预览内选择五山/国际/大学城；设置中仍可自定义。17项正式门禁通过，新版已沿原资料打开。[打开新版](/Users/czy/ProjectManagement/Demo2.5.4/课间桌宠.app) · [应用ZIP](/Users/czy/ProjectManagement/Demo2.5.4/Demo2.5.4-Mac-AppleSilicon.zip)。

当前更新 **2.5.3 重新导入与覆盖课表**：课表校对中可明确选择替换全部旧课程，准备保存展示移除数量，确认后生效；修复空课表的过期设置版本冲突。[本版说明](docs/releases/Demo2.5.3.md) · [验证](docs/validation/demo2.5.3/README.md)。已通过17项正式门禁，35项哈希复核通过，新版已沿用原资料打开。[打开新版](/Users/czy/ProjectManagement/Demo2.5.3/课间桌宠.app) · [应用ZIP](/Users/czy/ProjectManagement/Demo2.5.3/Demo2.5.3-Mac-AppleSilicon.zip)。以下为旧版记录。

当前更新 **2.5.2 Dock入口修复**：普通App模式，关闭窗口/隐藏桌宠后Dock保留，点击恢复主窗口和桌宠，菜单栏同时保留。[本版说明](docs/releases/Demo2.5.2.md) · [本版验证](docs/validation/demo2.5.2/README.md)。17项正式门禁通过，35项哈希复核通过，新版已用原资料启动。[打开新版](/Users/czy/ProjectManagement/Demo2.5.2/课间桌宠.app) · [应用ZIP](/Users/czy/ProjectManagement/Demo2.5.2/Demo2.5.2-Mac-AppleSilicon.zip)。以下2.5.1记录作为已有版本保留。

2.5.1历史开发分支为 **`codex/demo2.5.1-ui-refinement`**，按已批准的[完整窗口与桌宠参考](docs/design/ui-redesign-v2/README.md)实施。[修改计划](docs/superpowers/plans/2026-10-30-ui-refinement-implementation.md) · [开发进度](docs/roadmap/Demo2.5-开发进度追踪表.md) · [本版说明](docs/releases/Demo2.5.1.md) · [当前验证](docs/validation/demo2.5.1/README.md)。2.5.1加入内置扩展安装引导与独立分发模式，已完成17项正式发布门禁并归档，35项SHA256复核通过，新版已用原资料重新打开；已有2.5.0归档保留。

日常操作仅在独立App：默认完整窗口，左侧导航固定，内容独立滚动；窄窗口保持左侧图标栏。今日、日程、任务、助手共用柔和蓝灰外观，设置位于底部。课表导入默认指定Chrome或已保存的Edge，图片/PDF和文字在下方展开；只有明确点击学校导入按钮才会打开外部浏览器。

桌宠默认只显示NaiWa角色；单击展开一个328×360待办窗口，列表与详情在同一窗口切换，勾选明确完成整个任务；不再显示顶部文字条或任务环。审批、日程提醒在面板内的“待确认”可达。原任务/步骤/计时/执行反馈/校对/冲突与确认流程保留；任务详情中的“编辑与执行”展开完整工具。

以下保留既有功能和协作历史资料；新版界面入口以以上说明为准。

已发布基线为 **Demo2.4.9 项目收尾与联合交付版**，在甲乙接通基准 `05e7981` 上开发，本地分支 `codex/demo2.4.9-project-completion`。现已增加学校校历批量停课/明确补课/精确撤销、显式课程与任务分类、匹配 deep/review 的偏好与课程类型准备规则，以及独立OCR准确率评测工具。原执行、档案、目标、复盘、计时、协商与权威规划链路继续共用。

[本版说明](docs/releases/Demo2.4.9.md) · [完整项目汇报与甲乙实现清单](docs/report/项目汇报-Demo2.4.9.md) · [汇报讲述提纲](docs/report/项目汇报讲述提纲-Demo2.4.9.md) · [GitHub历史与贡献证据](docs/report/项目历史与甲乙贡献证据-2026-10-30.md)

当前版本按 [发布流程](docs/releases/发布流程.md) 从源码独立构建、验证和打包，不要求任何历史基线。发布是否通过，以归档 `manifest.json` 和 `验证结果.json` 为准。真实OCR目前没有30份匿名标注/5种布局/完整输入覆盖，不能宣称95%；学校校历内容、实地转移耗时、Windows/Intel与长期使用仍需真实验收。[OCR评测说明](docs/validation/课表准确率评测说明.md)与[当前状态](docs/validation/ocr-acceptance-status.json)明确记录缺口。

[乙方接收复核](docs/roadmap/乙方交付接收与进度复核-Demo2.4.7.md)保留为接收时记录；此前“乙接口待交付”及“未接入生成”清单均为历史状态，当前交接以本轮清单和代码为准。

用户最新核心流程与本轮验收见 [核心使用流程补充](docs/roadmap/core-flow-2026-10-28.md)。当日排程、单次课程调整、统一冲突、每周硬禁排、软偏好及固定事实局部重排已接入；通勤候选仅使用已确认耗时。校历批量例外和执行事件已接通；学校通知内容与真实使用效果仍需实际资料验收。

后续双人协作以 Demo2.4 提交为共同基线，分工、接口、交接与验收见 [双人开发任务分配](docs/roadmap/demo2.4-two-person-plan.md)，分别领取 [甲：课表与排程](docs/roadmap/demo2.4-person-a.md) 和 [乙：执行与助手](docs/roadmap/demo2.4-person-b.md)。

后续开发已启动：首批增加“待办与日程 → 禁排时段”、规划说明和批准快照，优先适配华工图片/PDF课表。首批范围、使用方法与后续待办见 [开发进度与数据契约](docs/roadmap/m0-planning-foundation.md)；完整建设范围见 [开发任务书](docs/roadmap/demo2.2-development-taskbook.md)。

两批新增代码已合并打包为 Demo2.3，并完成 DeepSeek 真实联调；使用、验证与待完成的准确率验收见 [本批开发记录](docs/roadmap/t01-timetable-recognition.md)。后续每版按 [发布流程](docs/releases/发布流程.md) 自动验证、打包与清理缓存。

实际 FastAPI + React 应用，支持课表草稿确认、截图作业校对、可编辑步骤、确定性日程与 Deep Agents 聊天。默认本地个人模式，无需助手账号登录；学校登录由本人在浏览器完成。模型通过本人配置的在线服务调用。

## 双击打开

- 正式包入口：[Demo2.5.3](/Users/czy/ProjectManagement/Demo2.5.3/)；已有Demo2.5.2、Demo2.5.1及历史归档保留。
- `campus-pet/启动课间桌宠.command` 优先打开 VERSION 对应的发布包，未发布时会从源码构建。桌宠会启动所需后台，日常界面在App内完成。
- 根目录两个旧“启动课间助手”脚本和旧桌面打包副本已清理，避免误点。源码首次初始化及 Windows 构建所需的底层脚本仍保留在 `scripts/`，详见 [开发与初始化说明](docs/desktop.md)。
- 打开后直接进入“今日”。有旧资料时首次明确选择，之后免登录。模型可在“设置 → 模型连接”填写；已有OpenRouter配置不覆盖。
- 日程中点击“导入课表”，默认显示学校导入；扩展安装指引在底部展开。首次仍需用户在Chrome/Edge安装扩展一次。
- 桌宠右键“关闭与退出”提供仅退出桌宠或停止后台并退出；关闭App窗口后服务仍运行。重复启动复用已有服务。

详细步骤、资料位置、Windows PowerShell/macOS构建命令、扩展安装和备份见 [桌面使用说明](docs/desktop.md)。当前已实际构建并验证macOS arm64包，无需终端Python/Node运行环境；Windows/Intel Mac尚未原生验收，没有开发者签名、公证或公开发布。

## Mac 助手桌宠

当前使用原生 Mac 桌宠入口，支持角色动作、助手面板和课后作业询问，构建步骤见 [桌宠说明](campus-pet/README.md)。在课表周视图点击空白时间格，也可添加课程并校对保存。

## 源码开发

开发者需Python3.12、uv、Node22（22.12+），保留已有 `.env`：

```sh
uv sync --project backend --locked --python 3.12
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix extension ci
```

日常运行无需Vite；生产扩展构建和桌面包构建见桌面文档。需要热更新时macOS用 `sh scripts/dev.sh`，Windows PowerShell用 `./scripts/dev.ps1`。普通启动禁止使用包含fake model的测试服务器。

本地自动化覆盖真实API、SQLite、Deep Agents检查点和MV3扩展。本人学校DOM已有登录实测，OpenRouter Luna真实协议已验证；真实学校Chrome/Edge完整流程、真实中文作业截图准确率与Windows仍需外部验收，见 [进度](docs/progress.md)。

## 使用顺序

1. 在“设置”校对学期第 1 周周一、周数、节次开始/结束时间。真实课表包含第 22 周，不能沿用较短学期范围。
2. 按 [扩展安装与华工导入](docs/scut-import.md) 构建、加载 WXT 扩展。在“课表”点击导入；本人登录主入口、进入个人课表、选择学期并点击查询，然后回助手校对、确认保存。
3. 在“待办与日程”上传 PNG/JPEG/WebP（每张 ≤10 MiB、≤2000 万像素），同意识别；原图与多条作业草稿并排校对。缺失截止时间保持待确认。
4. 拆解步骤，校对预计分钟、依赖和完成标准后保存。在“今日”生成未来 7 天草稿，再确认计划；未安排事项显示原因。
5. 在“助手”聊天；数据库写入需要真实批准。刷新和重启后可恢复待确认会话；异常中断不会自动重做付费识别或写入。

[运行与部署](docs/run-and-deploy.md) · [验收流程](docs/acceptance.md) · [版本与 SDK 决策](docs/decisions.md)

## 验证

```sh
uv sync --project backend --locked --python 3.12
uv run --project backend --no-sync pytest backend/tests -q
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix extension ci
npm --prefix extension test
```

浏览器测试的构建参数和真实模型探针见验收文档。锁定传递依赖在 `backend/uv.lock`、`frontend/package-lock.json`、`extension/package-lock.json`，不运行自动升级。

## 开源复用

SQLAlchemy/Alembic 提供持久化与迁移；Deep Agents/LangChain/LangGraph 提供工具循环、确认中断和 SQLite 检查点；FullCalendar 标准版提供日历；assistant-ui 提供聊天组件，自定义薄 runtime 接 FastAPI SSE；TanStack Query、React Hook Form、shadcn/ui 风格的按钮与Radix Dialog组件提供界面基础；WXT/WebExtension/@webext-core/messaging 提供扩展与消息；DOMPurify、pandas/lxml 提供受限课表解析。

自写部分集中在华工实测 DOM 适配、学生任务服务、版本/幂等连接与确定性排程。SQLite 首版只支持一个后端进程，不启用多 worker。
