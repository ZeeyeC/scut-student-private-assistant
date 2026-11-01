"""Validated MCP transport and per-owner connection settings, no literature writes."""

import hashlib
import asyncio, json, os, re, sys, tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, NAMESPACE_URL, uuid5
from fastapi import HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient
from app import memories, store
from app.db import Resource
from app.db_sessions import sqlite_transaction

ALLOWED = {
    "zotero_search_items",
    "zotero_get_item_metadata",
    "zotero_get_item_fulltext",
    "zotero_get_annotations",
    "zotero_get_notes",
    "zotero_get_collections",
}
DEFAULTS = {"enabled": False, "mode": "local", "endpoint": ""}


def validate_endpoint(value):
    value = value.strip()
    try:
        p = urlsplit(value)
        if (
            not p.hostname
            or p.username
            or p.password
            or p.query
            or p.fragment
            or "\\" in value
            or any(ord(c) < 33 for c in value)
            or len(value) > 2048
        ):
            raise ValueError()
        if p.scheme != "https" and not (
            p.scheme == "http" and p.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError()
        _ = p.port
    except ValueError:
        raise HTTPException(
            422, "MCP地址须为HTTPS或本机HTTP，且不含账号、查询参数或片段"
        ) from None
    return value


def secret_path(config, owner):
    UUID(owner)
    folder = Path(config.agent_db_path).resolve().parent / ".connector-secrets"
    if folder.is_symlink():
        raise HTTPException(422, "凭据目录不能是符号链接")
    path = folder / (owner + ".json")
    if path.is_symlink():
        raise HTTPException(422, "凭据文件不能是符号链接")
    return path


def secret_binding(data, revision):
    return hashlib.sha256(
        json.dumps(
            {
                "mode": data.get("mode"),
                "endpoint": data.get("endpoint"),
                "revision": revision,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def read_token(config, owner, data=None, revision=None):
    p = secret_path(config, owner)
    if not p.exists():
        return ""
    try:
        record = json.loads(p.read_text())
        if data is not None and record.get("binding") != secret_binding(data, revision):
            return ""
        return record.get("zotero_token", "")
    except Exception:
        raise HTTPException(422, "文献连接凭据不可读取，请在设置中重新填写") from None


def write_token(config, owner, value, binding=None):
    p = secret_path(config, owner)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not value:
        p.unlink(missing_ok=True)
        return
    fd, name = tempfile.mkstemp(prefix=".zotero-", dir=p.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"zotero_token": value, "binding": binding}, f)
        os.chmod(name, 0o600)
        os.replace(name, p)
    finally:
        Path(name).unlink(missing_ok=True)


async def settings(db, owner):
    r = await db.get(Resource, str(uuid5(NAMESPACE_URL, "zotero-settings:" + owner)))
    return r


def view(r, token=False):
    return {
        **(r.data if r else DEFAULTS),
        "revision": r.revision if r else 0,
        "token_configured": bool(token),
        "available": True,
        "connected": None,
        "tools": sorted(ALLOWED),
        "read_only": True,
    }


async def save(db, owner, config, body):
    r = await settings(db, owner)
    if (r.revision if r else 0) != body.revision:
        raise HTTPException(409, "文献连接已变化，请刷新设置")
    await memories.idle(db, owner)
    if config.app_mode != "local":
        raise HTTPException(403, "文献连接仅适用于本机个人模式")
    endpoint = validate_endpoint(body.endpoint) if body.mode == "remote" else ""
    old = read_token(config, owner, r.data if r else DEFAULTS, r.revision if r else 0)
    new = (
        ""
        if body.clear_token or body.mode == "local"
        else (body.token.strip() if body.token else old)
    )
    if r and endpoint != r.data.get("endpoint") and not body.token:
        new = ""
    if not r:
        r = Resource(
            id=str(uuid5(NAMESPACE_URL, "zotero-settings:" + owner)),
            owner_id=owner,
            kind="zotero_settings",
            data={},
        )
        db.add(r)
        await db.flush()
    r.data = {"enabled": body.enabled, "mode": body.mode, "endpoint": endpoint}
    r.revision += 1
    await memories.epoch(db, owner)
    # API transaction commits file and metadata together from the caller.
    return r, old, new


def connection(config, data, token):
    if data["mode"] == "remote":
        import httpx

        def factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(
                headers=headers,
                timeout=timeout or 20,
                auth=auth,
                follow_redirects=False,
                trust_env=False,
            )

        return {
            "transport": "streamable_http",
            "url": validate_endpoint(data["endpoint"]),
            "headers": {"Authorization": "Bearer " + token} if token else {},
            "timeout": 15,
            "sse_read_timeout": 20,
            "httpx_client_factory": factory,
        }
    command = sys.executable
    args = (
        ["--zotero-mcp"]
        if getattr(sys, "frozen", False)
        else ["-m", "app.zotero_worker"]
    )
    env = {
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHON_DOTENV_DISABLED": "1",
        "ZOTERO_LOCAL": "true",
        "ZOTERO_BACKEND": "api",
        "ZOTERO_MCP_TOOLSETS": "none,-semantic",
        "ZOTERO_NO_CLAUDE": "true",
        "ZOTERO_API_KEY": "",
        "ZOTERO_LOCAL_API_KEY": "",
    }
    return {"transport": "stdio", "command": command, "args": args, "env": env}


async def invoke(config, data, token, name, args, test=False):
    if name not in ALLOWED:
        raise HTTPException(403, "仅允许只读文献工具")
    client = MultiServerMCPClient(
        {"zotero": connection(config, data, token)}, handle_tool_errors=False
    )
    try:
        async with asyncio.timeout(25):
            async with client.session("zotero") as session:
                names = set()
                cursor = None
                for _ in range(5):
                    tools = await session.list_tools(cursor=cursor)
                    names.update(t.name for t in tools.tools)
                    cursor = getattr(tools, "nextCursor", None)
                    if name in names or not cursor or len(names) > 500:
                        break
                if name not in names:
                    raise ValueError("Missing read tool")
                result = await session.call_tool(name, args)
                if result.isError:
                    raise ValueError("Tool failed")
                text = "\n".join(
                    block.text
                    for block in result.content
                    if getattr(block, "type", None) == "text"
                )
                if re.search(
                    r"(?im)^error(?:[: ]|$)|connection refused|failed to connect", text
                ):
                    raise ValueError("Upstream unavailable")
                if not text.strip():
                    raise ValueError("Empty response")
                if token:
                    text = text.replace(token, "[已隐藏凭据]")
                if config.model_api_key:
                    text = text.replace(config.model_api_key, "[已隐藏凭据]")
                return {
                    "text": text[:18000],
                    "truncated": len(text) > 18000,
                    "tool": name,
                    "tools": sorted(names & ALLOWED),
                    "untrusted": True,
                    "read_only": True,
                }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            422,
            "Zotero连接或读取失败：请确认Zotero已打开且允许本机连接，或检查远端MCP地址与凭据",
        ) from None


async def call(app, owner, name, args, test=False, extra=None):
    async with sqlite_transaction(app.state.sessions) as db:
        r = await settings(db, owner)
        data = dict(r.data) if r else dict(DEFAULTS)
        revision = r.revision if r else 0
        if app.state.config.app_mode != "local":
            raise HTTPException(403, "文献连接仅适用于本机个人模式")
        if not data["enabled"]:
            raise HTTPException(409, "请先在设置中启用并保存Zotero文献连接")
        token = read_token(app.state.config, owner, data, revision)
        generation = db.info.get("data_generations", {}).get(owner, 0)
    invoker = getattr(app.state, "zotero_invoker", invoke)
    result = await invoker(app.state.config, data, token, name, args, test=test)
    if extra:
        second = await invoker(
            app.state.config, data, token, extra[0], extra[1], test=test
        )
        result = {**result, "text": (result["text"] + "\n" + second["text"])[:18000]}
    async with sqlite_transaction(app.state.sessions) as db:
        current = await settings(db, owner)
        if db.info.get("data_generations", {}).get(owner, 0) != generation:
            raise HTTPException(409, "资料已清空，旧文献读取结果未使用")
        if not current or current.revision != revision or not current.data["enabled"]:
            raise HTTPException(409, "文献连接已变化，旧读取结果未使用")
    return result
