import asyncio
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text

from app import imports, store
from app.contracts import AssignmentExtraction, AssignmentJobRequest, ResourceView
from app.db import Resource
from app.model_gateway import normalize_extraction


def decode_image(raw):
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "图片超过 10 MiB")
    try:
        im = Image.open(BytesIO(raw))
        if im.format not in ("PNG", "JPEG", "WEBP"):
            raise HTTPException(422, "仅支持 PNG/JPEG/WebP")
        if im.width * im.height > 20000000:
            raise HTTPException(413, "图片超过 20 百万像素")
        im.load()
        im = ImageOps.exif_transpose(im).convert("RGB")
        out = BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "图片无效")


async def run_assignment_job(app, owner, jid):
    sessions = app.state.sessions
    async with sessions() as db:
        job = await store.owned(db, owner, jid, "job")
        asset = await store.owned(db, owner, job.data["asset_id"], "asset")
        courses = [store.view(c) for c in await store.rows(db, owner, "course")]
        raw = Path(app.state.config.upload_dir, asset.data["filename"]).read_bytes()
        reference = job.data.get("reference_time")
        job.data = {**job.data, "status": "running"}
        job.revision += 1
        await db.commit()
    try:
        async with asyncio.timeout(120):
            payload = await app.state.gateway.extract_assignments(
                raw, "image/png", courses, reference
            )
        payload = normalize_extraction(payload, courses, reference)
        payload["asset_id"] = asset.id
        async with sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            d = await imports.create_draft(
                db,
                owner,
                "assignment",
                payload,
                {"asset_id": asset.id, "reference_time": reference},
            )
            job = await store.owned(db, owner, jid, "job")
            job.data = {**job.data, "status": "done", "draft_id": d["id"]}
            job.revision += 1
            await db.commit()
    except Exception as exc:
        async with sessions() as db:
            job = await store.owned(db, owner, jid, "job")
            # Keep provider response bodies and secrets out of public errors.
            msg = (
                "模型未配置，请手工录入或联系部署者"
                if isinstance(exc, ValueError) and "external_input_required" in str(exc)
                else "模型识别失败或超时，请重试或手工录入"
            )
            job.data = {**job.data, "status": "failed", "error": msg}
            job.revision += 1
            await db.commit()


def assignment_router(config, get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.post("/assets", response_model=ResourceView)
    async def upload(
        file: UploadFile,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        raw = await file.read(10 * 1024 * 1024 + 1)
        clean = decode_image(raw)

        async def op():
            ident = str(uuid4())
            filename = ident + ".png"
            Path(config.upload_dir, filename).write_bytes(clean)
            r = Resource(
                id=ident,
                owner_id=str(user.id),
                kind="asset",
                data={
                    "filename": filename,
                    "mime_type": "image/png",
                    "sha256": store.digest(raw.hex()),
                },
            )
            db.add(r)
            await db.flush()
            return store.view(r)

        return await store.mutate(
            db, str(user.id), "upload", key, {"sha256": store.digest(raw.hex())}, op
        )

    @router.get("/assets/{rid}")
    async def asset(rid: str, user=Depends(current_user), db=Depends(get_db)):
        r = await store.owned(db, str(user.id), rid, "asset")
        return FileResponse(
            Path(config.upload_dir, r.data["filename"]),
            media_type=r.data.get("mime_type", "image/png"),
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @router.post("/assignment-jobs", response_model=ResourceView)
    async def recognize(
        request: Request,
        body: AssignmentJobRequest,
        background: BackgroundTasks,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        asset = await store.owned(db, str(user.id), body.asset_id, "asset")
        if asset.data.get("purpose") == "timetable":
            raise HTTPException(422, "课表原件请使用课表识别入口")

        async def op():
            r = Resource(
                id=str(uuid4()),
                owner_id=str(user.id),
                kind="job",
                data={
                    **body.model_dump(mode="json"),
                    "status": "queued",
                    "draft_id": None,
                    "error": None,
                },
            )
            db.add(r)
            await db.flush()
            return store.view(r)

        result = await store.mutate(
            db, str(user.id), "assignment-job", key, body.model_dump(mode="json"), op
        )
        r = await store.owned(db, str(user.id), result["id"], "job")
        queued = r.data["status"] == "queued"
        if queued:
            r.data = {**r.data, "status": "running"}
            r.revision += 1
        await db.commit()
        if queued:
            background.add_task(run_assignment_job, request.app, str(user.id), r.id)
        return result

    @router.get("/jobs/{rid}", response_model=ResourceView)
    async def job(rid: str, user=Depends(current_user), db=Depends(get_db)):
        return store.view(await store.owned(db, str(user.id), rid, "job"))

    @router.post("/drafts/assignment", response_model=ResourceView)
    async def manual(
        body: AssignmentExtraction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        if body.asset_id:
            await store.owned(db, str(user.id), body.asset_id, "asset")
        for item in body.items:
            if item.course_id:
                await store.owned(db, str(user.id), item.course_id, "course")

        async def op():
            return await imports.create_draft(
                db, str(user.id), "assignment", body.model_dump(mode="json")
            )

        return await store.mutate(
            db, str(user.id), "assignment-draft", key, body.model_dump(mode="json"), op
        )

    @router.get("/tasks", response_model=list[ResourceView])
    async def tasks(user=Depends(current_user), db=Depends(get_db)):
        return [store.view(t) for t in await store.rows(db, str(user.id), "task")]

    return router
