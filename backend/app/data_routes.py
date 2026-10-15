import base64
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import delete, select

from app import store
from app.db import Receipt, Resource


def data_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/data-export")
    async def export(
        user=Depends(current_user), db=Depends(get_db), request: Request = None
    ):
        resources = list(
            (
                await db.scalars(
                    select(Resource).where(Resource.owner_id == str(user.id))
                )
            ).all()
        )
        images = {
            r.id: base64.b64encode(
                Path(
                    request.app.state.config.upload_dir, r.data["filename"]
                ).read_bytes()
            ).decode()
            for r in resources
            if r.kind == "asset"
        }
        return {
            "schema_version": 1,
            "resources": [store.view(r) for r in resources],
            "images_png_base64": images,
        }

    @router.post("/data-delete")
    async def remove(
        body: dict,
        request: Request,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        if body.get("confirmation") != "删除我的所有数据":
            raise HTTPException(422, "请输入准确删除确认文字")
        resources = list(
            (
                await db.scalars(
                    select(Resource).where(Resource.owner_id == str(user.id))
                )
            ).all()
        )
        if any(
            r.kind == "agent_run"
            and r.data["status"] in ("queued", "running", "resume_queued")
            for r in resources
        ):
            raise HTTPException(409, "助手正在运行，请等待结束后删除")
        if any(
            r.kind == "job" and r.data["status"] in ("queued", "running")
            for r in resources
        ):
            raise HTTPException(409, "图片正在识别，请等待结束后删除")
        for r in resources:
            if r.kind == "agent_thread":
                await request.app.state.checkpointer.adelete_thread(r.id)
            if r.kind == "asset":
                Path(request.app.state.config.upload_dir, r.data["filename"]).unlink(
                    missing_ok=True
                )
        await db.execute(delete(Resource).where(Resource.owner_id == str(user.id)))
        await db.execute(delete(Receipt).where(Receipt.owner_id == str(user.id)))
        return {"deleted": True}

    return router
