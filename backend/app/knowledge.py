"""Canonical owned study sources. Derived indexes are never an authority."""

import asyncio
import hashlib
import re
import zipfile
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from app import memories, store
from app.db import Resource, now
from app.knowledge_contracts import *


def safe_filename(name):
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "资料文件名无效")
    return name


def validate_document(name, raw):
    fmt = SUPPORTED_EXTENSIONS.get(Path(name).suffix.lower())
    if not fmt:
        raise HTTPException(422, "仅支持 PDF、DOCX、PPTX、XLSX、TXT、MD 资料")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, "资料不能超过20 MiB")
    if not raw:
        raise HTTPException(422, "资料为空")
    if fmt == "pdf" and not raw.startswith(b"%PDF-"):
        raise HTTPException(422, "PDF内容与格式不符")
    if fmt in {"docx", "pptx", "xlsx"}:
        try:
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                members = archive.infolist()
                if (
                    len(members) > MAX_ZIP_MEMBERS
                    or sum(i.file_size for i in members) > MAX_ZIP_UNCOMPRESSED_BYTES
                ):
                    raise ValueError()
                for m in members:
                    if (
                        m.file_size > MAX_ZIP_SINGLE_MEMBER_BYTES
                        or m.flag_bits & 1
                        or m.filename.startswith(("/", "\\"))
                        or ".." in Path(m.filename).parts
                    ):
                        raise ValueError()
                    if m.file_size > max(1024 * 1024, m.compress_size * 500):
                        raise ValueError()
                expected = {
                    "docx": "word/document.xml",
                    "pptx": "ppt/presentation.xml",
                    "xlsx": "xl/workbook.xml",
                }[fmt]
                if (
                    expected not in archive.namelist()
                    or "[Content_Types].xml" not in archive.namelist()
                ):
                    raise ValueError()
                # Verify CRC/deflate before handing content to a third-party parser.
                if archive.testzip():
                    raise ValueError()
        except (ValueError, OSError, zipfile.BadZipFile, RuntimeError):
            raise HTTPException(422, "Office资料无效、加密或解压后过大") from None
    if fmt in {"txt", "md"}:
        try:
            text = raw.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError()
        except (UnicodeDecodeError, ValueError):
            raise HTTPException(422, "文本资料请保存为UTF-8编码") from None
    return fmt


def chunks_for(parts):
    chunks = []
    total = 0
    truncated = False
    for location, text in parts:
        text = text.strip()
        if not text:
            continue
        remaining = MAX_DOCUMENT_CHARS - total
        if remaining <= 0:
            truncated = True
            break
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        total += len(text)
        for start in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
            excerpt = text[start : start + CHUNK_SIZE].strip()
            if excerpt:
                chunks.append(
                    {"id": str(len(chunks) + 1), "text": excerpt, "location": location}
                )
    if not chunks:
        raise HTTPException(
            422, "没有可读取的文字；扫描件请转为文本PDF，作业截图可使用图片识别"
        )
    return chunks, truncated


def extract_document(path, fmt):
    if fmt == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise HTTPException(422, "请先解除PDF密码保护")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise HTTPException(413, "PDF页数过多，请拆分资料")
        parts = []
        total = 0
        for i, page in enumerate(reader.pages):
            content = page.extract_text() or ""
            parts.append((f"第{i + 1}页", content))
            total += len(content)
            if total >= MAX_DOCUMENT_CHARS:
                break
        return chunks_for(parts)
    if fmt in {"txt", "md"}:
        text = Path(path).read_text(encoding="utf-8-sig")
    else:
        from markitdown import MarkItDown

        text = MarkItDown(enable_plugins=False).convert(str(path)).text_content
    # Converted Office positions are paragraph positions, never fabricated page numbers.
    return chunks_for(
        [(f"段落{i + 1}", p) for i, p in enumerate(re.split(r"\n\s*\n", text))]
    )


def storage_path(config, owner, name):
    # Only generated paths can reach disk, even when loading old or restored resources.
    UUID(owner)
    relative = Path(name)
    if (
        len(relative.parts) != 3
        or relative.parts[:2] != ("knowledge", owner)
        or not re.fullmatch(
            r"[a-f0-9-]{36}\.(pdf|docx|pptx|xlsx|txt|md)", relative.name
        )
    ):
        raise HTTPException(422, "资料存储标识无效")
    base = Path(config.upload_dir).resolve()
    path = base / relative
    if (
        path.is_symlink()
        or any(parent.is_symlink() for parent in (path.parent, path.parent.parent))
        or not path.resolve().is_relative_to(base)
    ):
        raise HTTPException(422, "资料存储路径无效")
    return path


async def check_course(db, owner, course_id):
    if course_id:
        await store.owned(db, owner, course_id, "course")


async def ensure_capacity(db, owner):
    if len(await store.rows(db, owner, "knowledge_source")) >= MAX_SOURCES_PER_OWNER:
        raise HTTPException(422, "最多保存100份资料，请先整理")


async def create_document(db, owner, config, name, raw, course_id, key):
    name = safe_filename(name)
    fmt = validate_document(name, raw)
    fingerprint = {
        "filename": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "course_id": course_id,
    }
    replay = await store.replay(db, owner, "knowledge-document", key, fingerprint)
    if replay:
        return replay.result
    await check_course(db, owner, course_id)
    await ensure_capacity(db, owner)
    generation = db.info.get("data_generations", {}).get(owner, 0)
    # Release the authentication transaction before parsing; repeat all write checks after.
    await db.commit()
    ident = str(uuid4())
    storage = f"knowledge/{owner}/{ident}.{fmt}"
    path = storage_path(config, owner, storage)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    try:
        async with asyncio.timeout(45):
            chunks, truncated = await asyncio.to_thread(
                extract_document, str(path), fmt
            )
        from sqlalchemy import text

        await db.execute(text("BEGIN IMMEDIATE"))
        if db.info.get("data_generations", {}).get(owner, 0) != generation:
            raise HTTPException(409, "资料已清空，本次上传已取消，请重新选择")
        replay = await store.replay(db, owner, "knowledge-document", key, fingerprint)
        if replay:
            path.unlink(missing_ok=True)
            return replay.result
        await check_course(db, owner, course_id)
        await ensure_capacity(db, owner)

        async def op():
            r = Resource(
                id=ident,
                owner_id=owner,
                kind="knowledge_source",
                data={
                    "filename": name,
                    "title": name,
                    "format": fmt,
                    "course_id": course_id,
                    "chunks": chunks,
                    "storage_name": storage,
                    "created_at": now().isoformat(),
                    "truncated": truncated,
                    "untrusted": True,
                },
            )
            db.add(r)
            await db.flush()
            return {"id": r.id, "revision": r.revision}

        result = await store.mutate(
            db, owner, "knowledge-document", key, fingerprint, op
        )
        await db.commit()
        return result
    except BaseException as exc:
        path.unlink(missing_ok=True)
        if isinstance(exc, (HTTPException, asyncio.CancelledError)):
            raise
        raise HTTPException(
            422, "资料解析失败、超时或文件损坏，请导出副本后重试"
        ) from None


async def create_web(db, owner, body, key):
    payload = body.model_dump(mode="json")
    replay = await store.replay(db, owner, "knowledge-web", key, payload)
    if replay:
        return replay.result
    await check_course(db, owner, body.course_id)
    await ensure_capacity(db, owner)
    generation = db.info.get("data_generations", {}).get(owner, 0)
    await db.commit()
    from app.web_research import read_webpage

    page = await read_webpage(body.url)
    from sqlalchemy import text

    await db.execute(text("BEGIN IMMEDIATE"))
    if db.info.get("data_generations", {}).get(owner, 0) != generation:
        raise HTTPException(409, "资料已清空，本次网页保存已取消")
    await check_course(db, owner, body.course_id)
    await ensure_capacity(db, owner)

    async def op():
        chunks, truncated = chunks_for(
            [(f"网页段落{i + 1}", p) for i, p in enumerate(page["text"].split("\n\n"))]
        )
        title = (body.title or page["title"])[:255]
        r = Resource(
            owner_id=owner,
            kind="knowledge_source",
            data={
                "filename": title,
                "title": title,
                "format": "web",
                "course_id": body.course_id,
                "chunks": chunks,
                "url": page["url"],
                "created_at": now().isoformat(),
                "truncated": truncated,
                "untrusted": True,
            },
        )
        db.add(r)
        await db.flush()
        return {"id": r.id, "revision": r.revision}

    return await store.mutate(db, owner, "knowledge-web", key, payload, op)


async def search_sources(db, owner, query, source_ids=None, course_id=None, limit=8):
    if not query.strip() or len(query) > 500:
        raise HTTPException(422, "检索词应为1至500字")
    await check_course(db, owner, course_id)
    if source_ids is not None:
        for sid in source_ids:
            await store.owned(db, owner, sid, "knowledge_source")
    terms = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", query.casefold())[:200]
    hits = []
    records = []
    for r in await store.rows(db, owner, "knowledge_source"):
        if source_ids is not None and r.id not in source_ids:
            continue
        if course_id and r.data.get("course_id") != course_id:
            continue
        for c in r.data["chunks"]:
            score = sum(t in c["text"].casefold() for t in terms)
            ident = r.id + ":" + c["id"]
            records.append(
                {
                    "id": ident,
                    "revision": r.revision,
                    "data": {"key": "", "content": c["text"]},
                }
            )
            hits.append(
                {
                    "id": ident,
                    "revision": r.revision,
                    "source_id": r.id,
                    "chunk_id": c["id"],
                    "title": r.data["title"],
                    "filename": r.data["filename"],
                    "location": c["location"],
                    "text": c["text"],
                    "score": score / max(1, len(terms)),
                    "url": r.data.get("url"),
                    "untrusted": True,
                }
            )
    from app.integrations_routes import semantic_enabled

    flags = await memories.settings(db, owner)
    epoch = flags.data["privacy_epoch"] if flags else 0
    scores = {}
    index = db.info.get("semantic_index")
    if index and await semantic_enabled(db, owner) and records:
        generation = index.generation(owner + "/knowledge")
        await db.commit()
        scores = await index.rank(
            owner + "/knowledge", query, records, epoch, generation=generation
        )
        from sqlalchemy import text

        await db.execute(text("BEGIN IMMEDIATE"))
        db.expire_all()
        flags = await memories.settings(db, owner)
        current_epoch = flags.data["privacy_epoch"] if flags else 0
        if current_epoch != epoch:
            scores = {}
        current = {
            r.id: r.revision for r in await store.rows(db, owner, "knowledge_source")
        }
        hits = [h for h in hits if current.get(h["source_id"]) == h["revision"]]
    selected = []
    for h in hits:
        v = scores.get(h["id"], {})
        similarity = v.get("score", 0) if v.get("revision") == h["revision"] else 0
        if h["score"] or similarity >= 0.5:
            h["score"] += similarity * 2
            h.pop("id")
            h.pop("revision")
            selected.append(h)
    return {
        "items": sorted(
            selected, key=lambda h: (-h["score"], h["source_id"], h["chunk_id"])
        )[: min(8, limit)],
        "mode": "semantic+keyword" if scores else "keyword",
    }


async def delete_source(db, owner, config, rid, revision, index=None):
    r = await store.owned(db, owner, rid, "knowledge_source")
    store.revision(r, revision)
    await memories.idle(db, owner)
    if index:
        await index.clear_owner(owner)
    if r.data.get("storage_name"):
        storage_path(config, owner, r.data["storage_name"]).unlink(missing_ok=True)
    await memories.epoch(db, owner)
    await db.delete(r)
    await db.flush()
    return {"deleted": True, "id": rid}
