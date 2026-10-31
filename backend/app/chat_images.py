"""Durable chat image recognition. Only explicit, consented sends reach vision."""
import asyncio
from uuid import uuid4

from fastapi import HTTPException

from app import assignments, imports, store
from app.db import Resource


class RecognitionFailed(Exception):
    pass


async def bind_image(db, owner, run, attachment):
    asset = await store.owned(db, owner, attachment.asset_id, "asset")
    if asset.data.get("purpose") == "timetable":
        raise HTTPException(422, "课表图片请使用课表导入")
    if asset.data.get("chat_thread_id") not in (None, run.data["thread_id"]):
        raise HTTPException(409, "图片已属于另一会话，请重新选择图片")
    if asset.data.get("chat_run_id"):
        raise HTTPException(409, "图片已发送，请在原消息中重试")
    asset.data = {**asset.data, "chat_thread_id": run.data["thread_id"], "chat_run_id": run.id}
    job = Resource(id=str(uuid4()), owner_id=owner, kind="job", data={
        **attachment.model_dump(mode="json"), "thread_id": run.data["thread_id"],
        "run_id": run.id, "status": "queued", "draft_id": None, "error": None,
    })
    db.add(job)
    run.data = {**run.data, "job_id": job.id, "draft_id": None}


async def prepare_image(app, owner, rid):
    # Imported lazily to keep the existing agent module independent at startup.
    from app.agent import transaction, emit
    async with transaction(app) as db:
        run = await store.owned(db, owner, rid, "agent_run")
        if run.data["status"] == "cancelled":
            raise asyncio.CancelledError()
        if run.data.get("draft_id"):
            return await imports.review_view(db, owner, await store.owned(db, owner, run.data["draft_id"], "draft"))
        job = await store.owned(db, owner, run.data["job_id"], "job")
        asset = await store.owned(db, owner, job.data["asset_id"], "asset")
        filename, reference = asset.data["filename"], job.data.get("reference_time")
        courses = [store.view(c) for c in await store.rows(db, owner, "course")]
        aid = asset.id
        job.data = {**job.data, "status": "running", "error": None}
        job.revision += 1
        await emit(db, owner, rid, "tool_started", {"name": "recognize_assignment_image"})
    try:
        payload = await assignments.extract_assignment_payload(app, filename, aid, courses, reference)
    except Exception as exc:
        message = assignments.recognition_error_message(exc)
        async with transaction(app) as db:
            job = await store.owned(db, owner, run.data["job_id"], "job")
            if job.data["status"] != "cancelled":
                job.data = {**job.data, "status": "failed", "error": message}
                job.revision += 1
        raise RecognitionFailed(message) from None
    async with transaction(app) as db:
        run = await store.owned(db, owner, rid, "agent_run")
        job = await store.owned(db, owner, run.data["job_id"], "job")
        if run.data["status"] == "cancelled" or job.data["status"] == "cancelled":
            raise asyncio.CancelledError()
        if not run.data.get("draft_id"):
            draft = await imports.create_draft(db, owner, "assignment", payload, {
                "thread_id": run.data["thread_id"], "run_id": rid, "job_id": job.id,
                "asset_id": aid, "reference_time": reference,
            })
            run.data = {**run.data, "draft_id": draft["id"]}
            job.data = {**job.data, "status": "done", "draft_id": draft["id"]}
            job.revision += 1
            await emit(db, owner, rid, "draft_ready", draft)
        else:
            draft = await imports.review_view(db, owner, await store.owned(db, owner, run.data["draft_id"], "draft"))
        return draft
