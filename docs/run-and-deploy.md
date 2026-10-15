# 运行、同一后端与备份恢复

日常本地使用优先见 [桌面入口与扩展向导](desktop.md)，默认免助手登录。以下源码命令供开发者热更新，服务器共享模式须显式选择。

## 环境与逐条启动

Python 3.12；Node 22.x；uv 0.11.19 为本次实测版本。Windows/macOS 都从项目根目录执行，复制 `.env.example` 时保留已有 `.env`。

第一个终端（两系统通用）：

```sh
uv sync --project backend --locked --python 3.12
uv run --project backend --no-sync uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
```

第二个终端：

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Web 地址 http://127.0.0.1:5173；API 文档 http://127.0.0.1:8000/docs。普通启动不能使用 `tests.e2e_server:app`，该入口含明确测试替身。

`.env` 的 `PUBLIC_ORIGIN` 必须与实际访问 origin 完全一致，包含协议和端口；localhost 与 127.0.0.1 不是同一 origin。密钥只读于后端，禁止 VITE_MODEL_API_KEY。修改模型配置后重启 API。

## 同一后端跨端使用

所有浏览器访问同一后端才共享数据和 Agent 检查点；Windows 与 macOS 各自启动独立 SQLite 不会同步。生产构建 `npm --prefix frontend run build` 后，FastAPI 会从 `frontend/dist` 同源提供 SPA，省去开发 Vite。

准备配置：`APP_MODE=shared`、`PUBLIC_ORIGIN=https://你的实际域名`、`SECURE_COOKIE=true`、数据库和上传目录指向持久磁盘。首个账号注册后可设 `REGISTRATION_ENABLED=false`；此开关不代替 HTTPS 和个人访问控制。扩展每台机器均需使用同一 PUBLIC_ORIGIN 重新构建、加载。Safari 可登录同一 Web 管理数据，当前不提供 Safari 扩展。

`deploy/Dockerfile`、`deploy/compose.yaml`、`deploy/Caddyfile` 是可审查的部署模板，当前机器没有 Docker，尚未实际构建/部署。没有公开部署。本地开发 cookie 非 secure 仅服务回环地址，生产模板通过 Caddy HTTPS 同源反代（SSE flush_interval=-1）。SQLite 后端只启动一个进程；服务锁防止意外多进程。

用户自行批准部署后可从根目录设置 APP_DOMAIN 与 PUBLIC_ORIGIN，再使用 compose 模板。需检查该实际域名、磁盘备份、证书和网络访问；本次没有操作这些外部资源。

## 备份

先停止后端。备份脚本遇到活动服务锁会拒绝，避免业务库与检查点跨事务不一致；复制时使用 SQLite backup API，包括校验过的两库和私有 PNG，生成带 SHA256 清单的 ZIP。

```sh
uv run --project backend --no-sync python scripts/backup.py backup backups/campus-2026-10-15.zip
```

不覆盖同名备份。`.env` 密钥不在备份包里，请独立保管。备份含账号哈希、登录 token、课程、作业、聊天与图片，按个人私有数据保管。

恢复只能到空目录：

```sh
uv run --project backend --no-sync python scripts/backup.py restore backups/campus-2026-10-15.zip data-restored
```

随后修改 `.env`：

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./data-restored/campus.db
AGENT_DB_PATH=./data-restored/agent.db
UPLOAD_DIR=./data-restored/uploads
```

重启后本地模式自动恢复选定资料，共享模式重新登录；核对课程、图片、任务和待确认 Agent 会话。测试已实际将暂停等待确认的 Deep Agents 检查点随备份恢复，再批准一次写入，重复批准不重复保存。GUI “导出本人数据”是 JSON 导出，不等于完整备份恢复包。

## 常见问题

- 409：其他设备更新了版本，刷新后重新校对；旧草稿不会覆盖新事实。
- “未检测到扩展”：检查扩展目录、origin、浏览器是否 Chrome/Edge，并刷新助手与学校标签页。
- 503 external_input_required：缺对应实测学校适配；不要用任意 URL 绕过校验。
- 无课程时间：在设置补开学周一及全部使用的节次，不填写猜测的钟点时间。
- 模型失败：检查 API key、供应商可访问性和模型图片/工具能力；失败保持草稿或待识别状态，不写学生任务。
