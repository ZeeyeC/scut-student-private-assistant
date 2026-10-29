# 课间 · 华工学生助手

本源码开发候选 **Demo2.4.7**：课程/冲突、重复硬禁排、软偏好、容量、方案比较、固定事实局部重排、显式日常候选和风险检查。选择和接受经过原草稿校对确认后保存。正式应用以工作区README为准。

[本版说明](docs/releases/Demo2.4.7.md) · [甲独立规划接口](docs/roadmap/a3-a6-independent-planning.md) · [需要乙交付的清单](docs/roadmap/乙方需提供的交接清单.md) · [局部重排](docs/roadmap/a4-calendar-replanning.md) · [容量](docs/roadmap/a3-planning-capacity.md) · [重复硬禁排](docs/roadmap/a3-weekly-constraints.md) · [统一冲突](docs/roadmap/a2-unified-conflicts.md) · [课程分段](docs/roadmap/a1-course-intervals.md)

用户最新核心流程与本轮验收见 [核心使用流程补充](docs/roadmap/core-flow-2026-10-28.md)。当日排程、单次课程调整、统一冲突、每周硬禁排、软偏好及固定事实局部重排已接入；通勤候选仅使用已确认耗时。完整学期例外和乙方执行事件联调继续按任务书推进。

后续双人协作以 Demo2.4 提交为共同基线，分工、接口、交接与验收见 [双人开发任务分配](docs/roadmap/demo2.4-two-person-plan.md)，分别领取 [甲：课表与排程](docs/roadmap/demo2.4-person-a.md) 和 [乙：执行与助手](docs/roadmap/demo2.4-person-b.md)。

后续开发已启动：首批增加“待办与日程 → 禁排时段”、规划说明和批准快照，优先适配华工图片/PDF课表。首批范围、使用方法与后续待办见 [开发进度与数据契约](docs/roadmap/m0-planning-foundation.md)；完整建设范围见 [开发任务书](docs/roadmap/demo2.2-development-taskbook.md)。

两批新增代码已合并打包为 Demo2.3，并完成 DeepSeek 真实联调；使用、验证与待完成的准确率验收见 [本批开发记录](docs/roadmap/t01-timetable-recognition.md)。后续每版按 [发布流程](docs/releases/发布流程.md) 自动验证、打包与清理缓存。

实际 FastAPI + React 应用，支持课表草稿确认、截图作业校对、可编辑步骤、确定性日程与 Deep Agents 聊天。默认本地个人模式，无需助手账号登录；学校登录由本人在浏览器完成。模型通过本人配置的在线服务调用。

## 双击打开

- 当前正式 Mac 日常入口：双击工作区 `Demo2.4.6/课间桌宠.app`。源码 VERSION 为 Demo2.4.7 候选，完整浏览器回归仍有一条读取超时；候选未正式发布，暂存 App 不替代正式入口。`campus-pet/启动课间桌宠.command` 优先打开 VERSION 对应的发布包，未发布时会从源码构建。桌宠会启动所需后台；浏览器可以同时访问 `http://127.0.0.1:5173/` 使用 Web UI，无需再启动另一个助手。
- 根目录两个旧“启动课间助手”脚本和旧桌面打包副本已清理，避免误点。源码首次初始化及 Windows 构建所需的底层脚本仍保留在 `scripts/`，详见 [开发与初始化说明](docs/desktop.md)。
- 打开后直接进入“今日”。有旧资料时首次明确选择，之后免登录。模型可在“设置 → 模型连接”填写；已有OpenRouter配置不覆盖。
- 点击“导入华工课表”立即显示分步向导，含首次扩展安装、打开目录、检测、本人进入课表、校对与保存。首次仍需用户在Chrome/Edge安装扩展一次。
- GUI的“停止助手”停止后台服务；关闭网页后服务仍运行。重复启动复用已有服务。

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
