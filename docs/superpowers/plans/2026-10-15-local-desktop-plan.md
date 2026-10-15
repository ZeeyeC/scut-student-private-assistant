# Local Desktop A Implementation Plan

> Execution: superpowers:executing-plans，用户已明确授权本会话直接执行已确认A方案。

Goal: 本地免登录、带环境桌面入口、课表导入向导。
Spec: docs/superpowers/specs/2026-10-15-local-desktop-design.md

约束：保留已有修改与个人配置；原数据不合并删除；localhost仅本机；复用FastAPI Users/PyInstaller/WXT；保存前确认；无需Vite日常运行；不发布/推送/改学校业务。项目无Git仓库，原地保留修改，不初始化Git。Ruling: 用户已批准完整A设计和执行，记录spec/plan后连续实施，避免重复索要设计许可。

- [x] 1. Local identity：backend/app/local_mode.py、db.py、config.py、main.py、迁移0002；先写backend/tests/test_local_mode.py证明无登录新库、旧资料选择、重启owner、Host/远程/CSRF拒绝，shared回归。
- [x] 2. GUI本地入口与设置：frontend/src/LocalMode.tsx、App.tsx、Settings.tsx；先写本地GUI Playwright场景；新库自动进入今日，旧资料明确选择，模型设置无密钥回显。
- [x] 3. Import wizard：frontend/src/BrowserImport.tsx与ImportGuide.tsx，复用现有会话状态机；实际检测后才进入开页；未安装图文、复制地址/路径、打开目录、刷新恢复/取消/过期，聊天走同一引导。Vitest/Playwright验证。
- [x] 4. Launcher/package：backend/app/launcher.py、paths.py、scripts/desktop_entry.py、build-desktop.py、desktop.spec及Windows/mac入口，锁定PyInstaller。先写启动器纯逻辑测试再实现。构建macOS arm64 onedir .app，隔离目录启动；验证不依赖源码/系统Python与Node、不含个人密钥/数据、重复启动/停止。Windows脚本与原生CI job仅提供，不声称实测。
- [x] 5. Integrated verification：全套pytest、前端/扩展typecheck/build/unit、本地GUI+共享回归、真实bundle启动。一次独立只读review，修复重要问题。更新README、run/deploy、extension指南、progress和桌面交付说明；迁移运行中本项目实例到本地模式，保留原库。

Ledger: docs/progress.md 追加每步的实际命令、结果和rulings。已有服务结束后运行需要独占5173端口的测试；仅停止已核对属于本项目的进程。

Completion: 本机实施/验证完成，原生macOS arm64包已交付并运行；Windows/Intel Mac和真实学校扩展等external_input_required如实保留。一次独立review发现3项重要问题均RED→GREEN修复，最终59 pytest通过、7不同GUI场景通过、最终bundle自检通过。无Git原地交付，不执行commit/merge/push。
