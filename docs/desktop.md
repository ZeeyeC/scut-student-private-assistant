# 本地桌面入口（A方案）

## 本项目现在怎么打开

macOS 双击项目根目录的 `启动课间助手.command`。它优先运行已经构建的 `dist/desktop/课间助手.app` 中的原生程序，明确使用本项目原有 `.env` 和数据库；不需要另装 Python/Node。终端可能短暂显示，随后在 Chrome/Edge 打开 `http://127.0.0.1:5173`。若没有这两种浏览器，使用系统默认浏览器，课表导入时仍需切换到 Chrome/Edge。

Windows 在该系统完成原生构建后，双击根目录 `启动课间助手.cmd`，会运行 `dist/desktop/CampusCompanion/CampusCompanion.exe` 并使用项目原资料。本次只有macOS arm64产物；Windows脚本、原生CI配置已提供，尚无Windows实机/产物验收。

助手直接进入“今日”，不再要求注册登录。若旧库有账号，首次选择要继续使用的资料或新建独立资料；旧资料保留，不自动合并删除。选定后保持相同身份。学校统一认证仍由本人登录。

关闭浏览器页面后本地助手仍运行。在“设置 → 模型连接”下方点击“停止助手”可停止服务；有正在处理的请求会拒绝停止。再次双击入口会重新启动。运行中重复打开只打开现有服务；若5173被别的服务或另一份资料占用，会显示错误，不杀其他程序。错误文件为资料目录下 `desktop-error.txt`，运行日志为 `desktop.log`。

## 分发给另一位用户

macOS Apple Silicon：复制整个 `课间助手.app` 到可长期保留的位置，再双击。不要只拷贝里面的可执行文件；程序包含自己的Python3.12、库、前端和预构建扩展。当前约127MiB，为本机构建/ad-hoc签名，没有开发者证书签名和Apple公证；未对外发布。Intel Mac须在对应架构另行构建，本次未验证。

Windows：在Windows原生构建后分发整个 `CampusCompanion` 文件夹，其中 `.exe` 和 `_internal` 须一起保留。不能用macOS产物直接在Windows运行。没有微软签名/安装器和商店发布。

独立双击 `.app/.exe` 使用系统个人资料目录，不自动读取某个源码项目的私有配置：

- macOS：`~/Library/Application Support/CampusCompanion`
- Windows：`%LOCALAPPDATA%\CampusCompanion`

该目录存放 `data/campus.db`、`data/agent.db`、`data/uploads`、`model.env`、`desktop-extension` 和日志。扩展复制到稳定目录；升级程序不删除个人数据库。不要把扩展安装到临时解压目录或 `.app` 内部。

源码项目入口使用项目根目录，扩展稳定副本为 `desktop-extension`，原 `extension/` 源码完整保留。两种入口属于不同资料位置，不自动同步；当前本人已有配置请使用项目根目录双击入口。切换时先从GUI停止正在运行的另一实例。

## 模型配置

源码项目保留已有根目录 `.env`；独立分发版首次在“设置 → 模型连接”填写，存入个人目录的 `model.env`，不需要手工找隐藏文件。保存后下一次请求生效，密钥留空保留原值，页面不会回显密钥；多页面保存发生版本冲突时需刷新重试。

本人OpenRouter配置：

```dotenv
MODEL_PROVIDER=openai
MODEL_BASE_URL=https://openrouter.ai/api/v1
TEXT_MODEL=openai/gpt-6-luna
VISION_MODEL=openai/gpt-6-luna
MODEL_API_KEY=填写本人的OpenRouter密钥
```

应用和数据库在本机；文本与截图仍调用配置的在线模型，需要网络并可能计费。学校课表提取不调用模型。个人密钥、课程、作业和图片不打进桌面包。

## 首次课表导入

1. 在Chrome/Edge打开助手，点击“课表 → 导入华工课表”，或在助手聊天请求导入。
2. 弹窗自动检测当前浏览器扩展。没有扩展时显示两个浏览器地址、开发者模式、加载解压扩展和真实扩展目录；点击“打开扩展文件夹”定位。
3. 将对应的 `chrome://extensions` 或 `edge://extensions` 复制到浏览器地址栏，开启开发者模式，加载该整个文件夹。首次加载后刷新助手，再重新检测。
4. 显示“扩展已连接”后点击“打开教务并继续”。实际扩展回执到达后才显示教务已打开。
5. 本人登录主入口、完成验证码，找到“学生课表查询 / 个人课表”，选择学年和学期并点击查询。扩展等待表格稳定，只提取课程字段。
6. 回到助手校对课程/周次/节次/地点和变更，经过“校对完成，准备保存 → 确认保存”后入库。关闭弹窗不取消，明确的“取消导入”才取消；刷新可恢复有效导入。

Safari可使用本地Web管理课程和任务，首版不提供Safari扩展。安装和学校页面流程仍需在目标用户Chrome/Edge实际验收，模拟测试不代表该验收。

## 本地备份

先在GUI停止助手。个人目录完整备份可直接复制整个资料目录到私有位置；包含课程、作业、图片、检查点和模型密钥，按私密资料保管。恢复到一个新的空资料目录，再用 `--data-dir` 指向它；不覆盖运行中的原库。

项目开发环境另提供带SHA256校验的双库/图片ZIP：`scripts/backup.py`，命令见run-and-deploy。该ZIP不包含 `.env/model.env`，密钥另行保管。GUI JSON导出不是完整检查点备份。

## 开发者原生构建

在目标系统安装Python3.12、uv和Node22，项目根目录运行：

```sh
uv sync --project backend --locked --python 3.12 --group desktop
uv run --project backend --no-sync python scripts/build-desktop.py
```

PowerShell同样执行这两条命令。脚本构建正式前端、固定学校适配的WXT生产扩展，再用锁定的PyInstaller6.22.3打包；不复制个人.env、数据库或测试fixture。脚本同时生成对应ZIP；macOS使用ditto保留.app符号链接与权限，CI上传ZIP。`--skip-web`仅供明确已构建正式资源的开发验证。未触发CI、发布或推送。

macOS独立运行自检：

```sh
backend/.venv/bin/python scripts/verify-desktop.py 'dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion'
```

自检要求5173空闲，使用临时资料和无Python/Node的PATH，验证静态GUI、扩展权限、无嵌入密钥、会话/设置持久化、重复启动、跨源拒绝、重启与正常停止；不访问学校或调用模型。Windows自检用 `backend\.venv\Scripts\python.exe` 和原生 `.exe` 路径；本机尚未执行Windows命令。
