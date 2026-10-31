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
            if r.kind == "asset" and r.data.get("mime_type", "image/png") == "image/png"
        }
        files = {}
        for r in resources:
            if r.kind == "asset":
                names = [
                    r.data["filename"],
                    *[p["filename"] for p in r.data.get("pages", [])],
                ]
                for name in names:
                    files[name] = base64.b64encode(
                        Path(request.app.state.config.upload_dir, name).read_bytes()
                    ).decode()
        return {
            "schema_version": 2,
            "resources": [store.view(r) for r in resources],
            "images_png_base64": images,
            "asset_files_base64": files,
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
        checkpoint_ids = {r.id for r in resources if r.kind == "agent_thread"}
        checkpoint_ids.update(r.data.get("checkpoint_id", r.data["thread_id"]) for r in resources if r.kind == "agent_run")
        for checkpoint_id in checkpoint_ids:
            await request.app.state.checkpointer.adelete_thread(checkpoint_id)
        for r in resources:
            if r.kind == "asset":
                for name in [
                    r.data["filename"],
                    *[p["filename"] for p in r.data.get("pages", [])],
                ]:
                    Path(request.app.state.config.upload_dir, name).unlink(
                        missing_ok=True
                    )
        await db.execute(delete(Resource).where(Resource.owner_id == str(user.id)))
        await db.execute(delete(Receipt).where(Receipt.owner_id == str(user.id)))
        return {"deleted": True}

    return router
