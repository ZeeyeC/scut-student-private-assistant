"""A small desktop entrypoint: bundled Python, local API and the user's browser."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from dotenv import dotenv_values

from app.config import Config
from app.paths import resource_root, user_data_dir
from app.processes import process_alive

ORIGIN = "http://127.0.0.1:5173"


def desktop_config(root: Path, resources: Path, *, project: bool):
    root = root.resolve()
    settings = root / (".env" if project else "model.env")
    # All fields are explicit so ambient shell variables cannot redirect a desktop
    # launch to a shared service, a different database or an unexpected API key.
    values = {name: field.get_default() for name, field in Config.model_fields.items()}
    values.update(
        {
            k.lower(): v
            for k, v in dotenv_values(settings).items()
            if k.lower() in values and v is not None
        }
    )
    values.update(
        app_mode="local",
        public_origin=ORIGIN,
        secure_cookie=False,
        settings_file=str(settings),
    )
    database = values["database_url"]
    if not database.startswith("sqlite+aiosqlite:///"):
        raise ValueError("桌面版仅支持本机 SQLite 数据库")
    database_path = Path(database.split("///", 1)[1])
    if not database_path.is_absolute():
        database_path = root / database_path
    values["database_url"] = "sqlite+aiosqlite:///" + str(database_path.resolve())
    for name in ("agent_db_path", "upload_dir"):
        path = Path(values[name])
        values[name] = str((path if path.is_absolute() else root / path).resolve())
    adapter = Path(
        values["scut_adapter_path"] or "config/scut-undergraduate-2026-10-14.json"
    )
    values["scut_adapter_path"] = str(
        (adapter if adapter.is_absolute() else resources / adapter).resolve()
    )
    values["extension_dir"] = str(root / "desktop-extension")
    return Config(_env_file=None, **values)


def service_identity(config):
    paths = [config.database_url, str(Path(config.agent_db_path).resolve())]
    return {
        "application": "campus-companion",
        "desktop_protocol": 1,
        "mode": config.app_mode,
        "database_id": hashlib.sha256(json.dumps(paths).encode()).hexdigest()[:24],
    }


def stage_extension(resources: Path, root: Path):
    source = resources / "extension" / ".output" / "chrome-mv3"
    destination = root / "desktop-extension"
    if not (source / "manifest.json").is_file():
        raise RuntimeError("桌面包缺少课表扩展，请重新构建")
    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".extension-", dir=root))
    old = root / ".extension-previous"
    try:
        shutil.copytree(source, temporary, dirs_exist_ok=True)
        shutil.rmtree(old, ignore_errors=True)
        if destination.exists():
            destination.rename(old)
        try:
            temporary.rename(destination)
        except OSError:
            if old.exists() and not destination.exists():
                old.rename(destination)
            raise
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return destination


def launch_arguments(root: Path, *, project: bool, frozen: bool):
    command = [sys.executable] if frozen else [sys.executable, "-m", "app.launcher"]
    command += ["--serve", "--data-dir", str(root)]
    if project:
        command.append("--project")
    return command


def probe():
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            ORIGIN + "/api/healthz", timeout=1
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("5173 端口已被其他服务占用，请先关闭该服务") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None
    except (ValueError, OSError) as exc:
        raise RuntimeError("5173 端口返回了无法识别的服务") from exc


def same_service(config):
    health = probe()
    if health is None:
        return False
    if any(health.get(key) != value for key, value in service_identity(config).items()):
        raise RuntimeError(
            "5173 端口运行着其他服务或另一份资料。请先停止它，再打开本助手"
        )
    return True


def open_browser():
    # Prefer extension-capable browsers; keep the default-browser fallback explicit
    # in the install guide if neither Chrome nor Edge is present.
    if sys.platform == "darwin":
        for name in ("Google Chrome", "Microsoft Edge"):
            if (Path("/Applications") / f"{name}.app").exists():
                subprocess.Popen(
                    ["open", "-a", name, ORIGIN],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
    elif sys.platform == "win32":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            directory = Path(os.environ.get(variable, ""))
            for relative in (
                "Google/Chrome/Application/chrome.exe",
                "Microsoft/Edge/Application/msedge.exe",
            ):
                executable = directory / relative
                if executable.is_file():
                    subprocess.Popen(
                        [str(executable), ORIGIN],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return
    webbrowser.open(ORIGIN)


def serve(config):
    import uvicorn

    from app.main import create_app

    app = create_app(config)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=5173, proxy_headers=False, log_config=None
        )
    )
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()


def start(root: Path, resources: Path, *, project: bool, browser: bool):
    config = desktop_config(root, resources, project=project)
    root.mkdir(parents=True, exist_ok=True)
    if same_service(config):
        if browser:
            open_browser()
        return
    # A short startup lock coordinates double-clicks before the API is listening.
    lock = root / ".desktop-start.lock"
    deadline = time.monotonic() + 120
    while True:
        try:
            with lock.open("x") as handle:
                handle.write(str(os.getpid()))
            break
        except FileExistsError:
            try:
                pid = int(lock.read_text())
                alive = process_alive(pid)
            except ValueError:
                alive = False
            if not alive:
                lock.unlink(missing_ok=True)
                continue
            if same_service(config):
                if browser:
                    open_browser()
                return
            if time.monotonic() > deadline:
                raise RuntimeError("另一个启动过程尚未完成，请查看 desktop.log")
            time.sleep(0.25)
    try:
        if same_service(config):
            if browser:
                open_browser()
            return
        stage_extension(resources, root)
        env = os.environ.copy()
        if getattr(sys, "frozen", False):
            # A new independent PyInstaller process must survive launcher exit.
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        else:
            env["PYTHONPATH"] = str(resources / "backend")
        options = (
            {"creationflags": subprocess.CREATE_NO_WINDOW}
            if sys.platform == "win32"
            else {"start_new_session": True}
        )
        log_path = root / "desktop.log"
        with log_path.open("ab") as log:
            log_path.chmod(0o600)
            child = subprocess.Popen(
                launch_arguments(
                    root, project=project, frozen=bool(getattr(sys, "frozen", False))
                ),
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                **options,
            )
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"本机服务启动失败，请查看 {log_path}")
            if same_service(config):
                if browser:
                    open_browser()
                return
            time.sleep(0.25)
        child.terminate()
        raise RuntimeError(f"启动超时，请查看 {log_path}")
    finally:
        lock.unlink(missing_ok=True)


def main():
    if "--time-mcp" in sys.argv[1:]:
        # PyInstaller windowed apps set sys.std* to None even with real pipes.
        # Restore the pipe streams only in this explicitly selected MCP child.
        if sys.stdin is None:
            sys.stdin = open(0, encoding="utf-8", closefd=False)
        if sys.stdout is None:
            sys.stdout = open(1, "w", encoding="utf-8", closefd=False)
        if sys.stderr is None:
            sys.stderr = open(2, "w", encoding="utf-8", closefd=False)
        from mcp_server_time import main as time_main

        sys.argv = [sys.argv[0]]
        time_main()
        return 0
    parser = argparse.ArgumentParser(description="课间：本机个人助手")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--project",
        action="store_true",
        help="Use an explicitly selected source project and its existing .env/data",
    )
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = (args.data_dir or user_data_dir()).expanduser().resolve()
    if args.project and not args.data_dir:
        parser.error("--project 需要明确指定 --data-dir，避免误用其他目录")
    try:
        if args.serve:
            serve(desktop_config(root, resource_root(), project=args.project))
        else:
            start(
                root, resource_root(), project=args.project, browser=False
            )
    except Exception as exc:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "desktop-error.txt").open("a", encoding="utf-8") as log:
            log.write(f"{type(exc).__name__}: {exc}\n")
        if sys.stderr:
            print(str(exc), file=sys.stderr)
        # Opening a plain error file also works in windowed bundles without Tk.
        if not args.no_browser and not args.serve:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-t", str(root / "desktop-error.txt")])
            elif sys.platform == "win32":
                os.startfile(str(root / "desktop-error.txt"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
