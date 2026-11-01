"""Durable chat image recognition. Only explicit, consented sends reach vision."""
import asyncio
from uuid import uuid4

from fastapi import HTTPException

from app import assignments, imports, store
from app.assignment_intake import deadline_declined
from app.db import Resource
from app.deadlines import suggest_assignment_deadlines


class RecognitionFailed(Exception):
    pass


def has_image_attachment(run_data: dict) -> bool:
    return bool(run_data.get("attachment") or run_data.get("attachments"))


def run_job_ids(run_data: dict) -> list[str]:
    if run_data.get("job_ids"):
        return list(run_data["job_ids"])
    if run_data.get("job_id"):
        return [run_data["job_id"]]
    return []


async def bind_images(db, owner, run, attachments, legacy=False):
    if not attachments or len(attachments) > 5:
        raise HTTPException(422, "单次最多发送 5 张作业图片")
    if len({a.asset_id for a in attachments}) != len(attachments):
        raise HTTPException(422, "同一批次不能重复添加相同图片")
    validated = []
    for attachment in attachments:
        asset = await store.owned(db, owner, attachment.asset_id, "asset")
        if asset.data.get("purpose") == "timetable":
            raise HTTPException(422, "课表图片请使用课表导入")
        if asset.data.get("chat_thread_id") not in (None, run.data["thread_id"]):
            raise HTTPException(409, "图片已属于另一会话，请重新选择图片")
        if asset.data.get("chat_run_id"):
            raise HTTPException(409, "图片已发送，请在原消息中重试")
        validated.append((attachment, asset))
    jobs = []
    for index, (attachment, asset) in enumerate(validated):
        asset.data = {
            **asset.data,
            "chat_thread_id": run.data["thread_id"],
            "chat_run_id": run.id,
        }
        job = Resource(
            id=str(uuid4()),
            owner_id=owner,
            kind="job",
            data={
                **attachment.model_dump(mode="json"),
                "thread_id": run.data["thread_id"],
                "run_id": run.id,
                "batch_index": index,
                "batch_size": len(validated),
                "status": "queued",
                "draft_id": None,
                "extracted_payload": None,
                "error": None,
            },
        )
        db.add(job)
        jobs.append(job)
    if legacy:
        run.data = {**run.data, "job_id": jobs[0].id, "draft_id": None}
    else:
        run.data = {**run.data, "job_ids": [j.id for j in jobs], "draft_id": None}


async def bind_image(db, owner, run, attachment):
    await bind_images(db, owner, run, [attachment], legacy=True)


async def prepare_image(app, owner, rid):
    # Imported lazily to keep the existing agent module independent at startup.
    from app.agent import emit, transaction

    async with transaction(app) as db:
        run = await store.owned(db, owner, rid, "agent_run")
        if run.data["status"] == "cancelled":
            raise asyncio.CancelledError()
        if run.data.get("draft_id"):
            draft_row = await store.owned(db, owner, run.data["draft_id"], "draft")
            if draft_row.data.get("status") != "pending":
                raise asyncio.CancelledError()
            return await imports.review_view(db, owner, draft_row)
        job_ids = run_job_ids(run.data)
        if not job_ids or len(job_ids) > 5:
            raise RecognitionFailed("图片批次数量无效")

    extracted_payloads = []
    for index, jid in enumerate(job_ids):
        async with transaction(app) as db:
            run = await store.owned(db, owner, rid, "agent_run")
            if run.data["status"] == "cancelled":
                raise asyncio.CancelledError()
            job = await store.owned(db, owner, jid, "job")
            if job.data["status"] == "cancelled":
                raise asyncio.CancelledError()
            cached = job.data.get("extracted_payload")
            if job.data["status"] == "done" and cached:
                extracted_payloads.append(
                    (
                        job.id,
                        job.data["asset_id"],
                        job.data.get("reference_time"),
                        cached,
                    )
                )
                continue
            asset = await store.owned(db, owner, job.data["asset_id"], "asset")
            filename = asset.data["filename"]
            reference = job.data.get("reference_time")
            courses = [store.view(c) for c in await store.rows(db, owner, "course")]
            aid = asset.id
            job.data = {**job.data, "status": "running", "error": None}
            job.revision += 1
            await emit(
                db,
                owner,
                rid,
                "tool_started",
                {
                    "name": "recognize_assignment_image",
                    "asset_id": aid,
                    "image_index": index,
                    "image_count": len(job_ids),
                },
            )
        try:
            payload = await assignments.extract_assignment_payload(
                app, filename, aid, courses, reference
            )
        except Exception as exc:
            base_message = assignments.recognition_error_message(exc)
            message = (
                f"第 {index + 1}/{len(job_ids)} 张图片识别失败：{base_message}"
                if len(job_ids) > 1
                else base_message
            )
            async with transaction(app) as db:
                job = await store.owned(db, owner, jid, "job")
                if job.data["status"] != "cancelled":
                    job.data = {**job.data, "status": "failed", "error": message}
                    job.revision += 1
                for pending_id in job_ids[index + 1:]:
                    pending = await store.owned(db, owner, pending_id, "job")
                    if pending.data["status"] == "queued":
                        pending.data = {**pending.data, "status": "failed", "error": "前一张图片识别失败，本图尚未处理；重试时继续"}
                        pending.revision += 1
            raise RecognitionFailed(message) from None
        async with transaction(app) as db:
            run = await store.owned(db, owner, rid, "agent_run")
            job = await store.owned(db, owner, jid, "job")
            if run.data["status"] == "cancelled" or job.data["status"] == "cancelled":
                raise asyncio.CancelledError()
            job.data = {
                **job.data,
                "status": "done",
                "error": None,
                "extracted_payload": payload,
            }
            job.revision += 1
            extracted_payloads.append((job.id, aid, reference, payload))

    total_items = sum(
        len(payload.get("items", [])) for _, _, _, payload in extracted_payloads
    )
    if total_items > 30:
        raise RecognitionFailed(
            f"单次图片批次最多合并 30 项作业（当前识别到 {total_items} 项），请分批发送图片"
        )

    async with transaction(app) as db:
        run = await store.owned(db, owner, rid, "agent_run")
        jobs = [await store.owned(db, owner, jid, "job") for jid in job_ids]
        if run.data["status"] == "cancelled" or any(
            j.data["status"] == "cancelled" for j in jobs
        ):
            raise asyncio.CancelledError()
        if not run.data.get("draft_id"):
            s = await store.settings(db, owner)
            combined_items = []
            combined_warnings = []
            asset_ids = []
            for _, aid, ref, payload in extracted_payloads:
                asset_ids.append(aid)
                resolved_part = suggest_assignment_deadlines(payload, s.data, ref)
                for item in resolved_part.get("items", []):
                    combined_items.append({**item, "source_asset_id": aid})
                for warning in resolved_part.get("warnings", []):
                    if warning not in combined_warnings:
                        combined_warnings.append(warning)
            refs = {ref for _, _, ref, _ in extracted_payloads}
            shared_ref = extracted_payloads[0][2] if len(refs) == 1 else None
            combined_payload = {
                "items": combined_items,
                "warnings": combined_warnings,
                "asset_id": asset_ids[0],
                "asset_ids": asset_ids,
            }
            source = {
                "thread_id": run.data["thread_id"],
                "run_id": rid,
                "job_id": job_ids[0],
                "job_ids": job_ids,
                "asset_id": asset_ids[0],
                "asset_ids": asset_ids,
                "reference_time": shared_ref,
                "item_asset_ids": [item["source_asset_id"] for item in combined_items],
                "deadline_followup": "deferred" if deadline_declined(run.data.get("message", "")) else "pending",
            }
            draft = await imports.create_draft(
                db, owner, "assignment", combined_payload, source
            )
            run.data = {**run.data, "draft_id": draft["id"]}
            for job in jobs:
                job.data = {**job.data, "status": "done", "draft_id": draft["id"]}
                job.revision += 1
            await emit(db, owner, rid, "draft_ready", draft)
        else:
            draft = await imports.review_view(
                db, owner, await store.owned(db, owner, run.data["draft_id"], "draft")
            )
        return draft
