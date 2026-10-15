import json
import re
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException
from lxml import html
from pydantic import Field

from app import imports, store
from app.calendar import parse_week_expression
from app.contracts import ResourceView, StrictModel, Timetable
from app.db import Resource, now


class StartImport(StrictModel):
    school_id: Literal["scut"] = "scut"


class ImportEvent(StrictModel):
    event_id: str = Field(min_length=1, max_length=160)
    kind: Literal["opened", "waiting_timetable", "extracting", "failed"]
    revision: int
    error_code: str | None = Field(default=None, max_length=100)


class Capture(StrictModel):
    protocol_version: Literal[1] = 1
    revision: int
    adapter_version: str
    school_origin: str
    semester_label: str = Field(min_length=1, max_length=200)
    fragments: list[str] = Field(min_length=1, max_length=20)


def load_adapter(config):
    if not config.scut_adapter_path or not Path(config.scut_adapter_path).is_file():
        raise HTTPException(
            503, "external_input_required：当前华工课表入口和页面结构尚未实测"
        )
    adapter = json.loads(Path(config.scut_adapter_path).read_text())
    parsed = urlparse(adapter["entry_url"])
    observed_http_route = parsed.hostname == "xsjw2018.jw.scut.edu.cn" and (
        (parsed.path in ("", "/") and not parsed.query)
        or (
            parsed.path == "/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html"
            and parse_qs(parsed.query, keep_blank_values=True)
            == {"gnmkdm": ["N2151"], "layout": ["default"]}
        )
    )
    if (
        not adapter.get("verified")
        or not (parsed.hostname or "").endswith(".scut.edu.cn")
        or parsed.username
        or parsed.password
        or parsed.port
        or not (
            parsed.scheme == "https"
            or (parsed.scheme == "http" and observed_http_route)
        )
        or (parsed.query and not observed_http_route)
    ):
        raise HTTPException(503, "学校适配配置未核验")
    if adapter["school_origin"] != f"{parsed.scheme}://{parsed.netloc}":
        raise HTTPException(503, "学校入口与 origin 不符")
    return adapter


def parse_capture(fragments, adapter, week_count):
    if sum(len(f.encode()) for f in fragments) > 1048576 or len(fragments) > 20:
        raise ValueError("课表片段超过限制")
    all_courses = []
    table_count = 0
    row_count = 0
    allowed = {"table", "thead", "tbody", "tfoot", "tr", "th", "td", "span", "br"}
    for fragment in fragments:
        root = html.fromstring(fragment)
        for node in root.iter():
            if node.tag not in allowed or any(
                a not in ("rowspan", "colspan") for a in node.attrib
            ):
                raise ValueError("课表片段含非课表内容或资源地址")
        tables = root.xpath("self::table | .//table")
        table_count += len(tables)
        row_count += len(root.xpath("self::tr | .//tr"))
        if table_count > 20 or row_count > 2000:
            raise ValueError("表格或行数超过限制")
        for frame in pd.read_html(StringIO(fragment), flavor="lxml"):
            mapping = adapter["columns"]
            if not all(
                mapping[k] in frame.columns
                for k in ("name", "weekday", "weeks", "periods")
            ):
                raise ValueError("课表表头不符，请重新实测适配")
            for _, row in frame.iterrows():

                def value(k):
                    v = row.get(mapping.get(k, ""))
                    return "" if pd.isna(v) else str(v).strip()

                name = value("name")
                if not name:
                    continue
                weekday = adapter.get("weekday_map", {}).get(
                    value("weekday"), value("weekday")
                )
                periods = parse_week_expression(
                    re.sub("[节]", "", value("periods")), 30
                )
                course = {
                    "name": name,
                    "weekday": int(weekday),
                    "weeks": parse_week_expression(value("weeks"), week_count),
                    "periods": periods,
                    "location": value("location") or None,
                    "teacher": value("teacher") or None,
                    "campus": value("campus") or None,
                }
                course["source_key"] = store.digest(
                    {
                        "name": name,
                        "weekday": course["weekday"],
                        "periods": periods,
                        "weeks": course["weeks"],
                        "campus": course["campus"],
                        "source_id": value("source_id"),
                    }
                )[:24]
                all_courses.append(course)
    if not all_courses:
        raise ValueError("未读取到完整课程条目")
    return Timetable(
        courses=all_courses,
        completeness="partial",
        semester_label="待校对",
        warnings=["尚无本次捕获的分页/过滤完整性证明，不删除已有课程"],
    ).model_dump(mode="json")


async def start_import(db, owner, config):
    adapter = load_adapter(config)
    r = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="browser_import",
        data={
            "school_id": "scut",
            "status": "queued",
            "browser_opened_at": None,
            "expires_at": (now() + timedelta(minutes=15)).isoformat(),
            "extracting_at": None,
            "draft_id": None,
            "entry_url": adapter["entry_url"],
            "adapter_version": adapter["version"],
            "capture_hash": None,
            "error": None,
        },
    )
    db.add(r)
    await db.flush()
    return store.view(r)


async def get_import(db, owner, rid):
    r = await store.owned(db, owner, rid, "browser_import")
    if r.data["status"] not in ("completed", "failed", "cancelled", "expired"):
        if now() > datetime.fromisoformat(r.data["expires_at"]):
            r.data = {**r.data, "status": "expired"}
            r.revision += 1
        elif r.data["status"] == "extracting" and now() - datetime.fromisoformat(
            r.data["extracting_at"]
        ) > timedelta(seconds=30):
            r.data = {**r.data, "status": "failed", "error": "提取超时"}
            r.revision += 1
    return r


def active(r):
    if r.data["status"] in (
        "completed",
        "failed",
        "cancelled",
        "expired",
        "preview_ready",
    ):
        raise HTTPException(409, "导入已经结束")


def browser_router(config, get_db, current_user):
    router = APIRouter(prefix="/api/browser-imports")

    @router.post("", response_model=ResourceView)
    async def start(
        body: StartImport,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await start_import(db, str(user.id), config)

        return await store.mutate(
            db, str(user.id), "browser-start", key, body.model_dump(), op
        )

    @router.get("", response_model=list[ResourceView])
    async def current(user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(await get_import(db, str(user.id), r.id))
            for r in await store.rows(db, str(user.id), "browser_import")
        ]

    @router.get("/{rid}", response_model=ResourceView)
    async def status(rid: str, user=Depends(current_user), db=Depends(get_db)):
        return store.view(await get_import(db, str(user.id), rid))

    @router.post("/{rid}/events", response_model=ResourceView)
    async def event(
        rid: str,
        body: ImportEvent,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            r = await get_import(db, str(user.id), rid)
            active(r)
            store.revision(r, body.revision)
            allowed = {
                "opened": {"queued"},
                "waiting_timetable": {"queued", "waiting_login"},
                "extracting": {"waiting_timetable"},
                "failed": {
                    "queued",
                    "waiting_login",
                    "waiting_timetable",
                    "extracting",
                },
            }
            if r.data["status"] not in allowed[body.kind]:
                raise HTTPException(409, "导入事件顺序无效")
            data = dict(r.data)
            if body.kind == "opened":
                data.update(status="waiting_login", browser_opened_at=now().isoformat())
            elif body.kind == "extracting":
                data.update(status="extracting", extracting_at=now().isoformat())
            else:
                data.update(status=body.kind, error=body.error_code)
            r.data = data
            r.revision += 1
            return store.view(r)

        return await store.mutate(
            db,
            str(user.id),
            f"browser-event:{rid}",
            body.event_id,
            body.model_dump(),
            op,
        )

    @router.post("/{rid}/cancel", response_model=ResourceView)
    async def cancel(
        rid: str,
        body: dict,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            r = await get_import(db, str(user.id), rid)
            if r.data["status"] == "cancelled":
                return store.view(r)
            if r.data["status"] in ("completed", "expired"):
                raise HTTPException(409, "已结束")
            store.revision(r, body.get("revision"))
            r.data = {**r.data, "status": "cancelled"}
            r.revision += 1
            if r.data["draft_id"]:
                draft = await store.owned(db, str(user.id), r.data["draft_id"], "draft")
                draft.data = {**draft.data, "status": "cancelled"}
                draft.revision += 1
            return store.view(r)

        return await store.mutate(
            db, str(user.id), f"browser-cancel:{rid}", key, body, op
        )

    @router.post("/{rid}/capture", response_model=ResourceView)
    async def capture(
        rid: str,
        body: Capture,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            r = await get_import(db, str(user.id), rid)
            h = store.digest(body.fragments)
            if (
                r.data["status"] in ("preview_ready", "completed")
                and r.data["draft_id"]
                and r.data["capture_hash"] == h
            ):
                return store.view(
                    await store.owned(db, str(user.id), r.data["draft_id"], "draft")
                )
            active(r)
            store.revision(r, body.revision)
            if r.data["status"] != "extracting":
                raise HTTPException(409, "尚未进入提取阶段")
            adapter = load_adapter(config)
            if (
                body.adapter_version != adapter["version"]
                or body.school_origin != adapter["school_origin"]
            ):
                raise HTTPException(422, "学校适配版本/origin 不符")
            try:
                payload = parse_capture(
                    body.fragments,
                    adapter,
                    30,
                )
            except (ValueError, TypeError, KeyError) as e:
                raise HTTPException(422, str(e))
            payload["semester_label"] = body.semester_label
            settings = await store.settings(db, str(user.id))
            max_week = max(w for course in payload["courses"] for w in course["weeks"])
            if max_week > settings.data["week_count"]:
                payload["warnings"].append(
                    f"课程包含第 {max_week} 周；请先在设置中校对学期周数，再重新导入"
                )
            d = await imports.create_draft(
                db,
                str(user.id),
                "timetable",
                payload,
                {
                    "browser_session": rid,
                    "verified_full": False,
                },
            )
            r.data = {
                **r.data,
                "status": "preview_ready",
                "draft_id": d["id"],
                "capture_hash": h,
            }
            r.revision += 1
            return d

        return await store.mutate(
            db,
            str(user.id),
            f"browser-capture:{rid}",
            key,
            body.model_dump(mode="json"),
            op,
        )

    return router
