"""SCUT image/PDF input: local assets -> model candidates -> explicit review."""

import asyncio
import hashlib
import re
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
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app import imports, store
from app.calendar import course_intervals, parse_week_expression
from app.contracts import Course, DraftEdit, ResourceView
from app.db import Resource
from app.timetable_contracts import (
    TimetableJobRequest,
    TimetablePageExtraction,
    TimetableRecognition,
)
from app.timetable_documents import prepare_document


def signature(candidate, week_count):
    fields = (
        "name",
        "teacher",
        "campus",
        "location",
        "weekday",
        "weeks_text",
        "periods",
    )
    values = {k: candidate.get(k) for k in fields}
    try:
        values["weeks_text"] = parse_week_expression(
            values["weeks_text"] or "", week_count
        )
    except ValueError:
        pass
    return store.digest(values)


def merge_pages(extractions, week_count):
    candidates, warnings, labels = {}, [], []
    for page_number, raw in enumerate(extractions, 1):
        page = TimetablePageExtraction.model_validate(raw)
        if page.semester_label and page.semester_label not in labels:
            labels.append(page.semester_label)
        warnings.extend(f"第 {page_number} 页：{w}" for w in page.warnings)
        if not page.candidates:
            warnings.append(f"第 {page_number} 页未提取到课程，请核对原件是否遗漏")
        for item in page.candidates:
            c = item.model_dump(mode="json")
            for key in ("name", "teacher", "campus", "location", "weeks_text"):
                c[key] = c[key].strip() if c[key] else None
            c["periods"] = sorted(set(c["periods"]))
            uncertain = set(c["uncertain_fields"])
            for key in (
                "name",
                "teacher",
                "campus",
                "location",
                "weekday",
                "weeks_text",
                "periods",
            ):
                if not c[key]:
                    uncertain.add(key)
            try:
                parse_week_expression(c["weeks_text"] or "", week_count)
            except ValueError:
                uncertain.add("weeks_text")
            if any(p < 1 or p > 30 for p in c["periods"]):
                uncertain.add("periods")
            # A confident-looking value without source evidence still needs review.
            evidenced = {e["field"] for e in c["evidence"]}
            uncertain.update(
                k
                for k in ("name", "weekday", "weeks_text", "periods")
                if k not in evidenced
            )
            c["uncertain_fields"] = sorted(uncertain)
            for evidence in c["evidence"]:
                evidence["page"] = page_number  # Provider cannot retarget another page.
            key = signature(c, week_count)
            if key in candidates:
                old = candidates[key]
                old["evidence"].extend(
                    e for e in c["evidence"] if e not in old["evidence"]
                )
                old["uncertain_fields"] = sorted(
                    set(old["uncertain_fields"] + c["uncertain_fields"])
                )
            else:
                candidates[key] = {
                    **c,
                    "candidate_id": str(uuid4()),
                    "reviewed": False,
                    "excluded": False,
                }
    if len(labels) > 1:
        warnings.append("多页学期标识不一致，请确认这些页面是否属于同一学期")
    return TimetableRecognition.model_validate(
        {
            "semester_label": labels[0] if len(labels) == 1 else "",
            "candidates": list(candidates.values()),
            "warnings": warnings,
        }
    ).model_dump(mode="json")


def validate_review_edit(original, edited):
    old = {c["candidate_id"]: c for c in original["candidates"]}
    new = {c["candidate_id"]: c for c in edited["candidates"]}
    if old.keys() != new.keys() or any(
        c["evidence"] != old[k]["evidence"] for k, c in new.items()
    ):
        raise HTTPException(422, "原始证据和候选标识不可修改；不需要的课程请勾选不导入")


def reviewed_courses(payload, settings, asset_id, source_kind="ocr"):
    if not payload["semester_confirmed"] or not payload["semester_label"].strip():
        raise HTTPException(422, "请填写并确认适用学期")

    def normalize(s):
        return re.sub(r"\s+", "", s)

    if settings.get("semester_name") and normalize(
        settings["semester_name"]
    ) != normalize(payload["semester_label"]):
        raise HTTPException(422, "识别学期与设置中的学期名称不一致，请先核对")
    if not settings.get("week1_monday"):
        raise HTTPException(422, "请先在设置中填写学期第一周周一，再校对保存")
    result = []
    for c in payload["candidates"]:
        if c["excluded"]:
            continue
        if not c["reviewed"] or c["uncertain_fields"]:
            raise HTTPException(
                422, f"请逐项校对并确认课程：{c['name'] or '未命名课程'}"
            )
        try:
            weeks = parse_week_expression(c["weeks_text"] or "", settings["week_count"])
            course = Course.model_validate(
                {
                    **{
                        k: c[k]
                        for k in (
                            "name",
                            "teacher",
                            "campus",
                            "location",
                            "weekday",
                            "periods",
                        )
                    },
                    "weeks": weeks,
                    "source_key": source_kind
                    + ":"
                    + store.digest({"asset": asset_id, "candidate": c["candidate_id"]}),
                }
            ).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(
                422, "课程名称、星期、周次或节次未补齐或不合法"
            ) from exc
        if not course["name"].strip() or any(
            p not in settings["periods"] and str(p) not in settings["periods"]
            for p in course["periods"]
        ):
            raise HTTPException(422, "课程名称为空或节次时间映射缺失，请先在设置中补齐")
        try:
            from datetime import date

            course_intervals(
                settings, course, date.fromisoformat(settings["week1_monday"])
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        result.append(course)
    if not result:
        raise HTTPException(422, "至少保留一门已校对的课程")
    return result


async def save_recognized_courses(db, owner, draft, payload, settings):
    source = draft.data["source"]
    text_input = draft.data["draft_kind"] == "timetable_text"
    if not text_input:
        await store.owned(db, owner, source["asset_id"], "asset")
    courses = reviewed_courses(
        payload,
        settings,
        draft.id if text_input else source["asset_id"],
        "text" if text_input else "ocr",
    )
    existing = await store.rows(db, owner, "course")

    # Exact normalized facts from a different input may already exist. Never delete
    # or replace other courses on the strength of an image's apparent completeness.
    def facts(c):
        return {
            k: c.get(k) or None
            for k in (
                "name",
                "teacher",
                "campus",
                "location",
                "weekday",
                "weeks",
                "periods",
            )
        }

    known = {store.digest(facts(r.data)): r for r in existing}
    ids = []
    for course in courses:
        key = store.digest(facts(course))
        if key not in known:
            r = Resource(id=str(uuid4()), owner_id=owner, kind="course", data=course)
            db.add(r)
            known[key] = r
        ids.append(known[key].id)
    return list(dict.fromkeys(ids))


async def preview_recognized_courses(db, owner, draft, payload, settings):
    text_input = draft.data["draft_kind"] == "timetable_text"
    courses = reviewed_courses(
        payload,
        settings,
        draft.id if text_input else draft.data["source"]["asset_id"],
        "text" if text_input else "ocr",
    )
    existing = await store.rows(db, owner, "course")
    fields = ("name", "teacher", "campus", "location", "weekday", "weeks", "periods")

    def facts(c):
        return store.digest({k: c.get(k) or None for k in fields})

    known = {facts(r.data) for r in existing}
    added, reused = [], []
    for course in courses:
        key = facts(course)
        (reused if key in known else added).append(course["name"])
        known.add(key)
    return {"added": added, "reused": reused, "existing_kept": len(existing)}


async def run_timetable_job(app, owner, jid):
    sessions = app.state.sessions
    try:
        async with sessions() as db:
            job = await store.owned(db, owner, jid, "job")
            asset = await store.owned(db, owner, job.data["asset_id"], "asset")
            settings = await store.settings(db, owner)
            week_count = settings.data["week_count"]
            pages = asset.data["pages"]
        extractions = []
        for i, page in enumerate(pages, 1):
            async with asyncio.timeout(120):
                raw = Path(app.state.config.upload_dir, page["filename"]).read_bytes()
                result = await app.state.gateway.extract_timetable(raw, page["text"], i)
            extractions.append(result)
            async with sessions() as db:
                job = await store.owned(db, owner, jid, "job")
                job.data = {**job.data, "completed_pages": i}
                job.revision += 1
                await db.commit()
        payload = merge_pages(extractions, week_count)
        async with sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            draft = await imports.create_draft(
                db,
                owner,
                "timetable_recognition",
                payload,
                {
                    "asset_id": asset.id,
                    "school_id": "scut",
                    "page_count": len(pages),
                    "original_extraction": payload,
                },
            )
            job = await store.owned(db, owner, jid, "job")
            job.data = {**job.data, "status": "done", "draft_id": draft["id"]}
            job.revision += 1
            await db.commit()
    except Exception as exc:
        async with sessions() as db:
            job = await store.owned(db, owner, jid, "job")
            error = (
                "模型未配置，请在设置中配置视觉模型，或使用手工添加课程"
                if isinstance(exc, ValueError) and "external_input_required" in str(exc)
                else "课表识别失败或超时，未保存课程；请重试或手工添加"
            )
            job.data = {**job.data, "status": "failed", "error": error}
            job.revision += 1
            await db.commit()


def timetable_recognition_router(config, get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.post("/drafts/{rid}/timetable-preview")
    async def preview(
        rid: str, body: DraftEdit, user=Depends(current_user), db=Depends(get_db)
    ):
        owner = str(user.id)
        draft = await store.owned(db, owner, rid, "draft")
        store.revision(draft, body.revision)
        if (
            draft.data["draft_kind"] not in {"timetable_recognition", "timetable_text"}
            or draft.data["status"] != "pending"
        ):
            raise HTTPException(409, "请选择未保存的课表识别草稿")
        payload = imports.validate_payload("timetable_recognition", body.payload)
        validate_review_edit(draft.data["payload"], payload)
        settings = await store.settings(db, owner)
        return await preview_recognized_courses(
            db, owner, draft, payload, settings.data
        )

    @router.get("/timetable-jobs", response_model=list[ResourceView])
    async def jobs(user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(r)
            for r in await store.rows(db, str(user.id), "job")
            if r.data.get("job_kind") == "timetable"
        ]

    @router.post("/timetable-assets", response_model=ResourceView)
    async def upload(
        file: UploadFile,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        raw = await file.read(20 * 1024 * 1024 + 1)
        digest = hashlib.sha256(raw).hexdigest()
        owner = str(user.id)
        # Replay before rendering: network retries do not create duplicate files.
        previous = await store.replay(
            db, owner, "timetable-upload", key, {"sha256": digest}
        )
        if previous is not None:
            return previous.result
        suffix, mime, decoded = await run_in_threadpool(prepare_document, raw)

        async def op():
            ident = str(uuid4())
            original = ident + "." + suffix
            paths = [Path(config.upload_dir, original)]
            pages = []
            try:
                paths[0].write_bytes(raw)
                for i, page in enumerate(decoded, 1):
                    filename = f"{ident}-page-{i}.png"
                    path = Path(config.upload_dir, filename)
                    paths.append(path)
                    path.write_bytes(page["png"])
                    pages.append(
                        {
                            "number": i,
                            "filename": filename,
                            "text": page["text"],
                            "type": page["type"],
                        }
                    )
                asset = Resource(
                    id=ident,
                    owner_id=owner,
                    kind="asset",
                    data={
                        "filename": original,
                        "mime_type": mime,
                        "sha256": digest,
                        "purpose": "timetable",
                        "pages": pages,
                    },
                )
                db.add(asset)
                await db.flush()
                return store.view(asset)
            except Exception:
                for path in paths:
                    path.unlink(missing_ok=True)
                raise

        return await store.mutate(
            db, owner, "timetable-upload", key, {"sha256": digest}, op
        )

    @router.get("/assets/{rid}/pages/{page}")
    async def page_image(
        rid: str, page: int, user=Depends(current_user), db=Depends(get_db)
    ):
        asset = await store.owned(db, str(user.id), rid, "asset")
        pages = asset.data.get("pages", [])
        if page < 1 or page > len(pages):
            raise HTTPException(404, "页面不存在")
        return FileResponse(
            Path(config.upload_dir, pages[page - 1]["filename"]), media_type="image/png"
        )

    @router.get("/timetable-assets/{rid}", response_model=ResourceView)
    async def get_asset(rid: str, user=Depends(current_user), db=Depends(get_db)):
        asset = await store.owned(db, str(user.id), rid, "asset")
        if asset.data.get("purpose") != "timetable":
            raise HTTPException(404, "课表原件不存在")
        return store.view(asset)

    @router.post("/timetable-jobs", response_model=ResourceView)
    async def recognize(
        request: Request,
        body: TimetableJobRequest,
        background: BackgroundTasks,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        asset = await store.owned(db, owner, body.asset_id, "asset")
        if asset.data.get("purpose") != "timetable":
            raise HTTPException(422, "请选择课表图片或 PDF")

        async def op():
            job = Resource(
                id=str(uuid4()),
                owner_id=owner,
                kind="job",
                data={
                    **body.model_dump(mode="json"),
                    "job_kind": "timetable",
                    "status": "queued",
                    "completed_pages": 0,
                    "total_pages": len(asset.data["pages"]),
                    "draft_id": None,
                    "error": None,
                },
            )
            db.add(job)
            await db.flush()
            return store.view(job)

        result = await store.mutate(
            db, owner, "timetable-job", key, body.model_dump(mode="json"), op
        )
        job = await store.owned(db, owner, result["id"], "job")
        queued = job.data["status"] == "queued"
        if queued:
            job.data = {**job.data, "status": "running"}
            job.revision += 1
        await db.commit()
        if queued:
            background.add_task(run_timetable_job, request.app, owner, job.id)
        return result

    return router
