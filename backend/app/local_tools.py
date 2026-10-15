"""Small fixed local desktop actions; no arbitrary file or shell access."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import set_key
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import Field, model_validator

from app import store
from app.contracts import StrictModel
from app.paths import resource_root


class EmptyAction(StrictModel):
    pass


class ModelSettings(StrictModel):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_provider: Literal["openai"] = "openai"
    text_model: str = Field(min_length=1, max_length=200)
    vision_model: str = Field(min_length=1, max_length=200)
    model_base_url: str = "https://openrouter.ai/api/v1"
    model_api_key: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def endpoint(self):
        url = urlsplit(self.model_base_url)
        if (
            url.username
            or url.password
            or url.query
            or url.fragment
            or not url.hostname
            or not (
                url.scheme == "https"
                or (
                    url.scheme == "http"
                    and url.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise ValueError("模型地址须为HTTPS或本机HTTP，不含账号、查询参数或片段")
        return self


def model_values(config):
    return {
        name: getattr(config, name)
        for name in (
            "model_provider",
            "text_model",
            "vision_model",
            "model_base_url",
            "model_api_key",
        )
    }


def model_status(config):
    values = model_values(config)
    key = values.pop("model_api_key")
    return {
        **values,
        "model_base_url": config.model_base_url or "https://api.openai.com/v1",
        "key_configured": bool(key),
        "revision": store.digest(model_values(config)),
    }


def persist_model_settings(path, values):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".model-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        temporary.write_text(
            path.read_text(encoding="utf-8") if path.exists() else "", encoding="utf-8"
        )
        for name, value in values.items():
            set_key(temporary, name.upper(), str(value))
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def extension_path(config):
    return (
        Path(config.extension_dir)
        if config.extension_dir
        else resource_root() / "extension" / ".output" / "chrome-mv3"
    )


def local_tools_router(config, current_user, get_db):
    router = APIRouter(prefix="/api/local", dependencies=[Depends(current_user)])

    @router.get("/model-settings")
    def model_settings():
        return model_status(config)

    @router.put("/model-settings")
    async def save_model_settings(
        body: ModelSettings,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def update():
            values = body.model_dump(exclude={"revision"})
            if not values["model_api_key"]:
                values["model_api_key"] = config.model_api_key
            if body.revision != model_status(config)[
                "revision"
            ] and values != model_values(config):
                raise HTTPException(409, "模型配置已更改，请刷新后重试")
            persist_model_settings(config.settings_file, values)
            for name, value in values.items():
                setattr(config, name, value)
            return model_status(config)

        # Only the request hash and safe result enter the existing replay ledger.
        return await store.mutate(
            db, str(user.id), "local-model-settings", key, body.model_dump(), update
        )

    @router.get("/extension-installation")
    def installation(request: Request):
        directory = extension_path(config).resolve()
        manifest = directory / "manifest.json"
        return {
            "available": manifest.is_file(),
            "directory": str(directory),
            "version": json.loads(manifest.read_text(encoding="utf-8")).get("version")
            if manifest.is_file()
            else None,
            "can_stop": hasattr(request.app.state, "request_shutdown"),
            "chrome_address": "chrome://extensions",
            "edge_address": "edge://extensions",
        }

    @router.post("/open-extension-folder")
    def open_folder(body: EmptyAction):
        directory = extension_path(config).resolve()
        if not (directory / "manifest.json").is_file():
            raise HTTPException(409, "扩展包尚未准备好，请重新构建桌面包")
        if sys.platform == "win32":
            os.startfile(str(directory))
        else:
            subprocess.Popen(
                ["open" if sys.platform == "darwin" else "xdg-open", str(directory)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return {"requested": True}

    @router.post("/shutdown")
    async def shutdown(request: Request, body: EmptyAction):
        if not hasattr(request.app.state, "request_shutdown"):
            raise HTTPException(409, "当前服务由终端启动，请在对应终端停止")
        if request.app.state.running_tasks:
            raise HTTPException(409, "助手仍在处理请求，请等待完成后停止")

        async def stop():
            await asyncio.sleep(0.5)
            request.app.state.request_shutdown()

        task = asyncio.create_task(stop())
        request.app.state.shutdown_task = task
        return {"stopping": True}

    return router
