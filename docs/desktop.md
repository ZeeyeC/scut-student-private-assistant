# 本地桌面入口（A方案）

## 本项目现在怎么打开

macOS 双击项目根目录的 `启动课间助手.command`。已有完整桌面包时直接运行 `dist/desktop/课间助手.app` 中的原生程序；首次下载源码时自动准备工具、安装依赖并构建，再启动助手。使用项目原有 `.env` 和数据库，不需要预先安装 Python/Node 或 Homebrew。终端显示首次构建进度，成功后在 Chrome/Edge 打开 `http://127.0.0.1:5173`。若没有这两种浏览器，使用系统默认浏览器，课表导入时仍需切换到 Chrome/Edge。

Windows 源码入口：下载完整仓库并解压到本地可写目录，双击根目录 `启动课间助手.cmd`。首次会自动初始化并构建，成功后运行 `dist/desktop/CampusCompanion/CampusCompanion.exe` 并使用项目资料；已有完整桌面包时直接启动，无需联网重新安装依赖。初始化脚本、自动化测试和原生 CI 已提供；当前开发机为 macOS，尚无本次 Windows 实机/产物验收。

助手直接进入“今日”，不再要求注册登录。若旧库有账号，首次选择要继续使用的资料或新建独立资料；旧资料保留，不自动合并删除。选定后保持相同身份。学校统一认证仍由本人登录。

关闭浏览器页面后本地助手仍运行。在“设置 → 模型连接”下方点击“停止助手”可停止服务；有正在处理的请求会拒绝停止。再次双击入口会重新启动。运行中重复打开只打开现有服务；若5173被别的服务或另一份资料占用，会显示错误，不杀其他程序。错误文件为资料目录下 `desktop-error.txt`，运行日志为 `desktop.log`。

## macOS 首次一键初始化

完整解压仓库到本机可写目录后，双击 `启动课间助手.command`。首次需要能访问 Node.js、Astral、npm 和 Python 包源的网络，下载及构建可能持续数分钟；后续启动复用完整桌面包，可离线打开本地界面，在线模型功能仍需要网络。

入口调用 `scripts/initialize-macos.sh`，兼容系统自带 Bash 3.2：

1. 检查 `.app` 的可执行程序、Python 动态库、前端和扩展；已有完整产物时直接启动。
2. 按 Mac 当前运行架构选择 Apple Silicon（arm64）或 Intel（x64）工具。优先复用 Node.js 22（至少 22.12）和 uv（至少 0.11.19）；缺少时从官方地址下载固定版本 Node.js 22.23.3、uv 0.11.19，并验证 SHA256 后解压到 `.tools/macos/`。
3. uv 在 `.tools/macos/python/` 准备 Python 3.12，在项目 `backend/.venv/` 安装锁定依赖；缓存位于 `.tools/macos/uv-cache/`。只改变初始化子进程的环境，不修改系统 PATH 或 shell 配置。
4. 调用已有 `scripts/build-desktop.py` 构建正式前端、华工扩展、当前架构的 `.app` 和 ZIP；以不含 Node/Python 的 PATH 执行程序 `--help` 及内置时间工具的空输入检查，确认打包程序能运行后才报告初始化成功。仅在 `.env` 缺失时从模板创建，不覆盖已有配置、个人数据或备份。
5. 成功后启动助手，扩展由启动器准备到 `desktop-extension/`。浏览器中首次“加载已解压的扩展程序”仍需本人操作。

失败窗口会保留提示，完整日志在 `.tools/macos-initialize.log`。下载失败自动重试三次；构建中断会留下未完成标记，下次双击重新初始化。系统文件锁防止并行构建，进程退出后自动释放，可直接重试。初始化不登录学校账号或调用模型。

源码更新后，先在助手 GUI 中停止服务，再在项目根目录终端重新构建并启动：

```sh
/bin/bash scripts/initialize-macos.sh --rebuild
```

仅初始化，不启动服务或打开浏览器：

```sh
/bin/bash scripts/initialize-macos.sh --no-launch
```

如果下载工具没有保留 `.command` 的执行权限，可在项目目录执行一次 `chmod +x 启动课间助手.command`；若系统要求确认打开下载的脚本，请通过 Finder 右键“打开”按系统提示处理。脚本不会移除系统隔离标记。

工具来源：[Node.js 官方发布目录](https://nodejs.org/dist/v22.23.3/)、[uv 官方发布](https://github.com/astral-sh/uv/releases/tag/0.11.19)。Apple Silicon 与 Intel 分别原生构建；本机验证结果和 CI 的实际运行结果应分别确认，不能用一种架构的测试代替另一种。

## Windows 首次一键初始化

需要 Windows 10/11 的 x64 环境、系统自带 Windows PowerShell 5.1，以及访问 Node.js、Astral、npm 和 Python 包源的网络。请先完整解压项目，例如放在 `C:\CampusCompanion`，再双击启动文件；不要直接在 ZIP 内运行。网络下载、依赖安装和打包首次可能持续数分钟，请等待完成。

`启动课间助手.cmd` 调用 `scripts/initialize-windows.ps1`，依次执行：

1. 检查完整桌面包。已存在则直接启动；首次或构建未完成时进入初始化。
2. 优先复用可用的 Node.js 22（至少 22.12）和 uv（至少 0.11.19）。缺少时从官方地址下载固定版本 Node.js 22.23.3 和 uv 0.11.19，校验 SHA256 后解压到 `.tools/windows/`；仅修改当前进程 PATH，不需要管理员权限或修改系统环境。
3. 由 uv 在 `.tools/python/` 准备 Python 3.12，并按 `backend/uv.lock` 安装桌面构建依赖；缓存放在 `.tools/uv-cache/`。
4. 调用现有 `scripts/build-desktop.py`，按 npm 锁文件构建正式前端与华工扩展，再构建当前 Windows 架构的桌面程序。
5. 仅在 `.env` 不存在时复制 `.env.example`。已有 `.env`、`model.env`、`data/` 和 `backups/` 不覆盖。成功后自动打开助手，在“设置 → 模型连接”填写自己的模型配置。

`.tools/`、运行数据和构建产物都在 Git 忽略规则中。初始化日志为 `.tools/initialize.log`；下载失败会自动重试三次，仍失败或安装/构建失败时窗口保留报错，修正网络或文件权限后再次双击即可。中断的初始化保留未完成标记，下一次会继续初始化，不会把不完整程序当作成功产物。避免同时运行两个初始化窗口。

源码更新后，需要先在 GUI 停止助手，再在项目根目录的 PowerShell 执行强制重新构建：

```powershell
.\启动课间助手.cmd -Rebuild
```

只初始化、不自动启动（例如 CI）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\initialize-windows.ps1 -NoLaunch
```

浏览器扩展首次仍需本人在 Chrome/Edge 中“加载已解压的扩展程序”；助手的导入向导会打开 `desktop-extension` 稳定目录。初始化不会安装浏览器扩展、登录学校账号或调用付费模型。当前锁定依赖（包括 tiktoken）没有 Windows ARM64 预构建包，脚本会在下载工具前明确拒绝 ARM64 和 32 位系统，不承诺这些架构的一键初始化。

工具来源：[Node.js 官方发布目录](https://nodejs.org/dist/v22.23.3/)、[uv 官方发布](https://github.com/astral-sh/uv/releases/tag/0.11.19)、[uv 管理 Python 的说明](https://docs.astral.sh/uv/guides/install-python/)。

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

打包通过 `scripts/package-desktop.py` 兼容项目路径中的方括号，确保 PyInstaller 正确加载依赖收集规则；每次重新构建会清理生成的 `build/desktop` 分析缓存。

初始化脚本的离线控制流、校验、失败重试和数据保留测试（不下载真实工具、不构建应用、不操作个人资料）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-initialize-windows.ps1
```

`.github/workflows/windows-initialization.yml` 在 Windows PowerShell 5.1 中运行这些测试。Mac 初始化测试使用 Python 标准库，测试目录均为临时合成资料，不联网：

```sh
python3 -m unittest discover -s scripts/tests -p 'test_initialize_macos.py'
```

`.github/workflows/macos-initialization.yml` 配置 Apple Silicon 和 Intel runner 运行脚本测试。手动触发的 `Desktop native build` 在 Mac 和 Windows 上均使用首次初始化入口执行原生构建及桌面自检，并移除 PATH 中的开发工具以覆盖自动下载路径。

macOS独立运行自检：

```sh
backend/.venv/bin/python scripts/verify-desktop.py 'dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion'
```

自检要求5173空闲，使用临时资料和无Python/Node的PATH，验证静态GUI、扩展权限、无嵌入密钥、会话/设置持久化、重复启动、跨源拒绝、重启与正常停止；不访问学校或调用模型。Windows自检用 `backend\.venv\Scripts\python.exe` 和原生 `.exe` 路径；本机尚未执行Windows命令。
