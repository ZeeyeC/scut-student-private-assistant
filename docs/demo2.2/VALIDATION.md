# Demo2.2 自检报告

验证日期：2026-10-18。平台：macOS / Apple Silicon。以隔离测试数据库和明确的测试模型验收，不读取个人资料或调用付费模型。

| 检查 | 结果 | 范围 |
| --- | --- | --- |
| 后端与初始化器 | 158 项通过，另含 5 个子测试 | API、持久化、草稿确认、排程、课后作业、日程提醒、启动与迁移 |
| 前端单元检查 | 12 项通过 | 状态整理、草稿和会话等基础逻辑 |
| 浏览器流程 | 10 项通过 | 作业补录恢复、审批定位、网站/文件快捷设置、课表与待办日程分离、排程确认 |
| 原生逻辑回归 | 通过 | 当天筛选、时区、跨午夜、缩写、布局、稳定补位、动画与提醒数据 |
| 原生 App 集成 | 54 项通过 | 真实 WebKit + API + SQLite，任务环、详情、完成保存、冲突恢复、提醒及既有功能 |
| 系统录屏 | 通过，约 60 秒 | 真实 App 的自动功能演示，已抽帧复核任务环、详情、自动补位和空状态，无声音 |

共 234 项计数检查通过，另有原生逻辑回归通过。前后端从当前源码完整构建，App 版本为 2.2.0；本地 ad-hoc 签名完整性检查通过，包内未发现个人配置或数据库文件。录屏中的操作由隔离演示模式自动执行，演示流程同时核对实际读取与保存结果。

复现命令（先按根 README 安装依赖并构建前端）：

```sh
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests scripts/tests -q
npm --prefix frontend test
PET_BROWSER_CHANNEL=bundled npx --prefix frontend playwright test --config=frontend/playwright.pet.config.ts
backend/.venv/bin/python campus-pet/tests/run_native_tests.py
backend/.venv/bin/python campus-pet/build.py
backend/.venv/bin/python campus-pet/verify.py
backend/.venv/bin/python campus-pet/record_demo.py --seconds 60
```

浏览器默认使用系统 Chrome；`PET_BROWSER_CHANNEL=bundled` 使用已安装的 Playwright Chromium。原生集成与录屏都使用专用端口 5189，不能同时运行；浏览器使用 5290。端口被占用时退出，不停止其他服务。录屏需要 macOS 已授予当前运行工具屏幕录制权限。

验收边界：本版未重新进行真实学校登录、真实模型付费调用、Intel Mac、Windows、多物理显示器及休眠唤醒验收。录屏自动执行演示流程，鼠标左右键由原生回归中的事件分发另行检查。
