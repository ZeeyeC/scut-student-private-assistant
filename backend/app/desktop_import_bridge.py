"""Import-only capabilities for an external browser with no App login cookie."""
import hashlib
import secrets
from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field

from app import browser_imports, store
from app.contracts import ResourceView, StrictModel
from app.db import Resource, now


class GrantRequest(StrictModel):
    # The native caller retains this secret. Receipts store only the request
    # digest and public grant metadata, never a recoverable bearer credential.
    client_token: str = Field(pattern=r"^[a-f0-9]{64}$")


class BridgeState(StrictModel):
    state: Literal["connecting", "extension_missing", "ready"]


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def desktop_import_router(config, get_db, current_user):
    router = APIRouter()

    @router.post("/api/browser-imports/{rid}/desktop-grant")
    async def issue(rid: str, body: GrantRequest, key: str = Header(alias="Idempotency-Key"), user=Depends(current_user), db=Depends(get_db)):
        owner = str(user.id)
        session = await browser_imports.get_import(db, owner, rid)
        browser_imports.active(session)

        async def op():
            for old in await store.rows(db, owner, "desktop_import_grant"):
                if old.data["import_id"] == rid and not old.data.get("revoked"):
                    old.data = {**old.data, "revoked": True}
                    old.revision += 1
            gid = str(uuid4())
            grant = Resource(id=gid, owner_id=owner, kind="desktop_import_grant", data={
                "import_id": rid, "token_hash": token_hash(gid + "." + body.client_token),
                "expires_at": session.data["expires_at"], "revoked": False,
                "consumed": False, "capture_key": None, "capture_digest": None,
            })
            db.add(grant)
            await db.flush()
            return {"grant_id": gid, "bridge_path": "/school-import/" + rid,
                    "expires_at": session.data["expires_at"], "status": session.data["status"]}

        return await store.mutate(db, owner, "desktop-grant:" + rid, key, body.model_dump(), op)

    async def authorized(rid, authorization, db):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "需要有效导入授权")
        token = authorization[7:]
        if len(token) > 120 or token.count(".") != 1:
            raise HTTPException(401, "导入授权无效")
        gid = token.split(".", 1)[0]
        grant = await db.get(Resource, gid)
        if not grant or grant.kind != "desktop_import_grant" or not secrets.compare_digest(grant.data["token_hash"], token_hash(token)):
            raise HTTPException(401, "导入授权无效")
        if grant.data["import_id"] != rid:
            raise HTTPException(404, "导入任务不存在")
        if grant.data.get("revoked") or now() >= datetime.fromisoformat(grant.data["expires_at"]):
            raise HTTPException(410, "导入授权已过期或被替换，请回App重试")
        session = await browser_imports.get_import(db, grant.owner_id, rid)
        if session.data["status"] in {"cancelled", "expired", "failed"}:
            raise HTTPException(410, "导入已取消、失败或过期")
        return grant, session

    @router.get("/api/desktop-import-bridge/{rid}")
    async def status(rid: str, authorization: str | None = Header(default=None), db=Depends(get_db)):
        grant, session = await authorized(rid, authorization, db)
        return {"session": store.view(session), "owner_id": grant.owner_id}

    @router.post("/api/desktop-import-bridge/{rid}/bridge-state", response_model=ResourceView)
    async def bridge_state(rid: str, body: BridgeState, authorization: str | None = Header(default=None), db=Depends(get_db)):
        grant, session = await authorized(rid, authorization, db)
        if grant.data["consumed"]:
            raise HTTPException(409, "捕获已完成，请回App校对")
        browser_imports.active(session)
        if session.data.get("desktop_bridge_status") != body.state:
            session.data = {**session.data, "desktop_bridge_status": body.state}
            session.revision += 1
        return store.view(session)

    @router.post("/api/desktop-import-bridge/{rid}/events", response_model=ResourceView)
    async def event(rid: str, body: browser_imports.ImportEvent, key: str = Header(alias="Idempotency-Key"), authorization: str | None = Header(default=None), db=Depends(get_db)):
        grant, _ = await authorized(rid, authorization, db)
        if grant.data["consumed"]:
            raise HTTPException(409, "捕获已完成，请回App校对")

        async def op():
            return await browser_imports.apply_import_event(db, grant.owner_id, rid, body)

        return await store.mutate(db, grant.owner_id, "browser-event:" + rid, body.event_id, body.model_dump(), op)

    @router.post("/api/desktop-import-bridge/{rid}/capture", response_model=ResourceView)
    async def capture(rid: str, body: browser_imports.Capture, key: str = Header(alias="Idempotency-Key"), authorization: str | None = Header(default=None), db=Depends(get_db)):
        grant, _ = await authorized(rid, authorization, db)
        payload = body.model_dump(mode="json")
        scope = "desktop-grant-capture:" + grant.id
        if grant.data["consumed"]:
            if grant.data["capture_key"] != key or grant.data["capture_digest"] != store.digest(payload):
                raise HTTPException(409, "导入授权已消费，不能提交另一份捕获")
            receipt = await store.replay(db, grant.owner_id, scope, key, payload)
            if receipt:
                return receipt.result
            raise HTTPException(409, "捕获收据不可用，请回App核对")

        async def op():
            draft = await browser_imports.apply_import_capture(db, grant.owner_id, rid, body, config)
            grant.data = {**grant.data, "consumed": True, "capture_key": key, "capture_digest": store.digest(payload)}
            grant.revision += 1
            return draft

        return await store.mutate(db, grant.owner_id, scope, key, payload, op)

    return router
