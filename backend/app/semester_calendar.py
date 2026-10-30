"""Reviewed semester batches over the canonical course/exception engine.

Batches are immutable audit snapshots. Undo restores the exact previous exception
payloads only after checking every row, and never rewrites a later adjustment.
The caller owns the surrounding transaction, receipt and settings bump.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from app import store
from app.calendar import (
    COURSE_INTERVAL_VERSION,
    expand_calendar,
    occupied_course_events,
)
from app.conflicts import detect_conflicts
from app.db import Resource, now
from app.planning_history import record_change
from app.semester_contracts import SemesterPayload

SEMESTER_VERSION = "semester-calendar-1"


def validate_semester_payload(payload):
    # Old manual JSON clients can omit the operation for an apply request.
    if isinstance(payload, dict) and "operation" not in payload:
        payload = {"operation": "apply", **payload}
    try:
        return (
            TypeAdapter(SemesterPayload)
            .validate_python(payload)
            .model_dump(mode="json")
        )
    except ValidationError as exc:
        raise HTTPException(
            422,
            "请明确课程、学校规则依据与作用范围；补课必须填写原日和目标日，不能自动推算",
        ) from exc


def _key(data):
    return (data["course_id"], data["date"])


def _snapshot(rows):
    return deepcopy([store.view(r) for r in rows])


def _versions(rows):
    return {r.id: r.revision for r in rows}


async def _sources(db, owner):
    s = await store.settings(db, owner)
    rows = {
        kind: await store.rows(db, owner, kind)
        for kind in [
            "course",
            "exception",
            "fixed_event",
            "plan_block",
            "scheduling_constraint",
            "semester_calendar_batch",
        ]
    }
    versions = {
        "settings": s.revision,
        **{kind: _versions(items) for kind, items in rows.items()},
    }
    return s, rows, versions


def _wall_shift(value, days, tz):
    """Keep local wall clock, reject an unconfirmed DST gap or repeated clock."""
    local = datetime.fromisoformat(value).astimezone(tz)
    naive = local.replace(tzinfo=None) + timedelta(days=days)
    candidates = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=tz, fold=fold)
        if (
            candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
            == naive
        ):
            if candidate.utcoffset() not in [c.utcoffset() for c in candidates]:
                candidates.append(candidate)
    if len(candidates) != 1:
        raise HTTPException(
            422, "补课目标包含夏令时缺失或重复时刻，请先用单次调课明确带时区时间"
        )
    return candidates[0].isoformat()


def _bounds(settings, exceptions):
    if not settings.get("week1_monday"):
        raise HTTPException(422, "请先配置学期第一周周一，再预览学校校历规则")
    anchor = date.fromisoformat(settings["week1_monday"])
    days = [anchor, anchor + timedelta(weeks=settings["week_count"], days=-1)]
    tz = ZoneInfo(settings["timezone"])
    for e in exceptions:
        for field in ["starts_at", "ends_at"]:
            if e.get(field):
                days.append(datetime.fromisoformat(e[field]).astimezone(tz).date())
    return min(days), max(days)


def _expand(settings, courses, exceptions):
    try:
        return expand_calendar(
            settings, courses, exceptions, *_bounds(settings, exceptions)
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, "请先补齐课表配置：" + str(exc)) from exc


async def _undo_batch(db, owner, payload, rows):
    batch = await store.owned(db, owner, payload["batch_id"], "semester_calendar_batch")
    if batch.data["operation"] != "apply":
        raise HTTPException(422, "请选择原校历批次撤销，撤销记录本身不能再次撤销")
    if any(b.data.get("undo_of") == batch.id for b in rows["semester_calendar_batch"]):
        raise HTTPException(409, "这个校历批次已经撤销")
    targets = {_key(c) for c in batch.data["targets"]}
    current = [r for r in rows["exception"] if _key(r.data) in targets]
    expected = batch.data["after"]
    if {r.id: r.revision for r in current} != {
        r["id"]: r["revision"] for r in expected
    } or {r.id: store.digest(r.data) for r in current} != {
        r["id"]: store.digest(r["data"]) for r in expected
    }:
        raise HTTPException(409, "批次中的课程已有后续调整，不能覆盖；请先核对每次课程")
    return batch


async def preview_semester(db, owner, payload):
    payload = validate_semester_payload(payload)
    s, rows, versions = await _sources(db, owner)
    courses = [store.view(r) for r in rows["course"]]
    exceptions = [deepcopy(r.data) for r in rows["exception"]]
    selected = None
    batch = None
    if payload["operation"] == "apply":
        selected = [
            await store.owned(db, owner, cid, "course") for cid in payload["course_ids"]
        ]
    else:
        batch = await _undo_batch(db, owner, payload, rows)
    existing = _expand(s.data, courses, exceptions)
    changes, mutations, targets = [], [], []
    undo_of = None
    if payload["operation"] == "apply":
        maps = {m["original_date"]: m["target_date"] for m in payload["mappings"]}
        if payload["action"] == "cancel":
            start, end = (
                date.fromisoformat(payload["start_date"]),
                date.fromisoformat(payload["end_date"]),
            )
        else:
            start, end = (
                min(map(date.fromisoformat, maps)),
                max(map(date.fromisoformat, maps)),
            )
        try:
            base = expand_calendar(
                s.data, [store.view(r) for r in selected], [], start, end
            )
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, "请先补齐课表配置：" + str(exc)) from exc
        base = [
            e
            for e in base
            if payload["action"] == "cancel" or e["original_date"] in maps
        ]
        if not base or (maps and set(maps) != {e["original_date"] for e in base}):
            raise HTTPException(
                422, "所选原课日期没有对应课程；请按原课表明确日期，不会顺延猜测"
            )
        if len(base) > 500:
            raise HTTPException(422, "单个校历批次最多调整500次课程，请缩小范围")
        for event in base:
            original = event["original_date"]
            key = event["course_id"], original
            targets.append({"course_id": key[0], "date": key[1]})
            before = [r for r in rows["exception"] if _key(r.data) == key]
            source = {
                "kind": "semester_calendar",
                "rule_kind": payload["rule_kind"],
                "reason": payload["reason"],
                "source_scope": payload["source_scope"],
                "original_date": original,
            }
            data = {
                "course_id": key[0],
                "date": original,
                "cancelled": payload["action"] == "cancel",
                "starts_at": None,
                "ends_at": None,
                "location": event.get("location"),
                "campus": event.get("campus"),
                "active": True,
                "confirmed": True,
                "source": source,
            }
            if payload["action"] == "move":
                target = maps[original]
                shift = (date.fromisoformat(target) - date.fromisoformat(original)).days
                tz = ZoneInfo(s.data["timezone"])
                # Check every occupied/teaching/break boundary before generating a batch.
                for field in [
                    "teaching_intervals",
                    "break_intervals",
                    "occupied_intervals",
                ]:
                    for interval in event[field]:
                        for endpoint in ["starts_at", "ends_at"]:
                            _wall_shift(interval[endpoint], shift, tz)
                data.update(
                    starts_at=_wall_shift(event["starts_at"], shift, tz),
                    ends_at=_wall_shift(event["ends_at"], shift, tz),
                )
                source.update(
                    target_date=target,
                    timezone=tz.key,
                    preserve_periods=True,
                    interval_snapshot={
                        "interval_version": event["interval_version"],
                        **{
                            field: [
                                {
                                    **deepcopy(interval),
                                    **{
                                        endpoint: _wall_shift(
                                            interval[endpoint], shift, tz
                                        )
                                        for endpoint in ("starts_at", "ends_at")
                                    },
                                }
                                for interval in event[field]
                            ]
                            for field in (
                                "teaching_intervals",
                                "break_intervals",
                                "occupied_intervals",
                            )
                        },
                    },
                )
            mutations.append(
                {
                    "target": targets[-1],
                    "before": _snapshot(before),
                    "replacement": data,
                }
            )
        target_keys = {_key(t) for t in targets}
        simulated = [e for e in exceptions if _key(e) not in target_keys]
        simulated.extend(m["replacement"] for m in mutations)
    else:
        undo_of = batch.id
        targets = deepcopy(batch.data["targets"])
        target_keys = {_key(t) for t in targets}
        simulated = [e for e in exceptions if _key(e) not in target_keys]
        simulated.extend(deepcopy(r["data"]) for r in batch.data["before"])
        for target in targets:
            mutations.append(
                {
                    "target": target,
                    "before": _snapshot(
                        [r for r in rows["exception"] if _key(r.data) == _key(target)]
                    ),
                    "restore": deepcopy(
                        [
                            r
                            for r in batch.data["before"]
                            if _key(r["data"]) == _key(target)
                        ]
                    ),
                }
            )
    after = _expand(s.data, courses, simulated)
    before_by_id, after_by_id = (
        {e["id"]: e for e in existing},
        {e["id"]: e for e in after},
    )
    ids = {f"{t['course_id']}:{t['date']}" for t in targets}
    names = {r.id: r.data["name"] for r in rows["course"]}
    for target in targets:
        eid = f"{target['course_id']}:{target['date']}"
        changes.append(
            {
                **target,
                "title": names.get(target["course_id"], "课程"),
                "before": before_by_id.get(eid),
                "after": after_by_id.get(eid),
            }
        )
    all_events = [{**e, "kind": "course"} for e in after]
    all_events.extend(
        {"id": r.id, "kind": "fixed_event", **r.data} for r in rows["fixed_event"]
    )
    report = detect_conflicts(all_events, s.data)
    report["issues"] = [
        i
        for i in report["issues"]
        if any(
            e.get("occurrence_id", e["id"]) in ids for e in [i["first"], i["second"]]
        )
    ]
    report.update(
        conflict_count=sum(i["severity"] == "conflict" for i in report["issues"]),
        pending_count=sum(i["severity"] == "pending" for i in report["issues"]),
        complete=True,
        configuration_warnings=[],
        timezone=s.data["timezone"],
    )
    affected, new_plan_conflicts = [], []
    occupied = [
        (label, e)
        for change in changes
        for label in ["before", "after"]
        for e in occupied_course_events([change[label]] if change[label] else [])
    ]
    for r in rows["plan_block"]:
        a, b = (
            datetime.fromisoformat(r.data["starts_at"]),
            datetime.fromisoformat(r.data["ends_at"]),
        )
        overlaps = [
            label
            for label, e in occupied
            if a < datetime.fromisoformat(e["ends_at"])
            and b > datetime.fromisoformat(e["starts_at"])
        ]
        if overlaps:
            view = {"id": r.id, "kind": "plan_block", **r.data}
            affected.append(view)
            if "after" in overlaps:
                new_plan_conflicts.append(view)
    result = {
        "schema_version": SEMESTER_VERSION,
        "interval_version": COURSE_INTERVAL_VERSION,
        "timezone": s.data["timezone"],
        "operation": payload["operation"],
        "undo_of": undo_of,
        "changes": changes,
        "targets": targets,
        "mutations": mutations,
        "versions": versions,
        "conflict_report": report,
        "affected_plans": affected,
        "plan_conflicts": new_plan_conflicts,
        "message": "仅按你确认的学校规则调整列出的原课。补课保留原节次及课间；已有学习安排、锁定项和执行记录保留，受影响安排需重新规划并确认。",
    }
    result["preview_hash"] = store.digest(result)
    return result


async def save_semester(db, owner, draft, payload):
    payload = validate_semester_payload(payload)
    if (
        draft.owner_id != owner
        or draft.kind != "draft"
        or draft.data.get("draft_kind") != "semester_calendar"
    ):
        raise HTTPException(404, "资源不存在")
    source = draft.data["source"]
    if store.digest(payload) != source.get("generated_hash"):
        raise HTTPException(422, "校历调整与预览绑定，请重新生成草稿")
    batch_id = str(uuid5(NAMESPACE_URL, f"semester-calendar:{owner}:{draft.id}"))
    previous = await db.get(Resource, batch_id)
    if previous:
        if previous.owner_id != owner or previous.data["payload_hash"] != store.digest(
            payload
        ):
            raise HTTPException(409, "校历确认记录不匹配")
        return previous.data["saved_ids"]
    if draft.data.get("status") != "pending":
        raise HTTPException(409, "草稿已经取消或失效")
    preview = source["preview"]
    if (
        preview.get("schema_version") != SEMESTER_VERSION
        or preview.get("interval_version") != COURSE_INTERVAL_VERSION
    ):
        raise HTTPException(409, "校历或课程展开规则已更新，请重新预览")
    if store.digest(
        {k: v for k, v in preview.items() if k != "preview_hash"}
    ) != preview.get("preview_hash"):
        raise HTTPException(409, "校历预览校验失败，请重新生成草稿")
    s, _, versions = await _sources(db, owner)
    store.revision(s, draft.data["source_revision"])
    if preview["versions"] != versions:
        raise HTTPException(409, "校历来源、课程或学习安排已变化，请重新预览")
    fresh = await preview_semester(db, owner, payload)
    if fresh["preview_hash"] != preview.get("preview_hash"):
        raise HTTPException(409, "校历预览与当前事实不一致，请重新生成草稿")
    before, after, saved_ids = [], [], []
    # SQLite legacy transaction mode does not BEGIN for SELECT. Ensure the
    # savepoint cannot become the outer transaction and commit on RELEASE.
    connection = await db.connection()
    if connection.dialect.name == "sqlite":
        raw = await connection.get_raw_connection()
        if not raw.driver_connection.in_transaction:
            await connection.exec_driver_sql("BEGIN")
    # A savepoint makes even an interrupted direct service caller all-or-nothing;
    # the normal API transaction also contains the receipt, draft and settings bump.
    async with db.begin_nested():
        for mutation in preview["mutations"]:
            before.extend(deepcopy(mutation["before"]))
            current = [
                await store.owned(db, owner, r["id"], "exception")
                for r in mutation["before"]
            ]
            if payload["operation"] == "apply":
                if current:
                    target = current[0]
                    target.revision += 1
                else:
                    target = Resource(
                        id=str(
                            uuid5(NAMESPACE_URL, f"{batch_id}:{mutation['target']}")
                        ),
                        owner_id=owner,
                        kind="exception",
                        revision=1,
                    )
                    db.add(target)
                data = deepcopy(mutation["replacement"])
                data["source"].update(draft_id=draft.id, batch_id=batch_id)
                data["confirmed_at"] = now().isoformat()
                target.data = data
                saved_ids.append(target.id)
                for duplicate in current[1:]:
                    if duplicate.data.get("active", True):
                        duplicate.data = {**duplicate.data, "active": False}
                        duplicate.revision += 1
                await db.flush()
                after.extend(_snapshot([target, *current[1:]]))
            else:
                restore = {r["id"]: r for r in mutation["restore"]}
                for row in current:
                    if row.id in restore:
                        row.data = deepcopy(restore[row.id]["data"])
                        row.revision += 1
                        saved_ids.append(row.id)
                        after.append(store.view(row))
                    else:
                        await db.delete(row)
                await db.flush()
        batch_data = {
            "schema_version": SEMESTER_VERSION,
            "operation": payload["operation"],
            "undo_of": preview["undo_of"],
            "draft_id": draft.id,
            "payload": payload,
            "payload_hash": store.digest(payload),
            "targets": preview["targets"],
            "before": deepcopy(before),
            "after": deepcopy(after),
            "saved_ids": saved_ids,
            "preview": deepcopy(preview),
            "confirmed_at": now().isoformat(),
        }
        db.add(
            Resource(
                id=batch_id,
                owner_id=owner,
                kind="semester_calendar_batch",
                data=batch_data,
            )
        )
        await db.flush()
        await record_change(
            db,
            owner,
            "semester_calendar_changed",
            batch_id,
            1,
            {
                "batch_id": batch_id,
                "operation": payload["operation"],
                "undo_of": preview["undo_of"],
                "before": before,
                "after": after,
                "preview": deepcopy(preview),
            },
        )
    return saved_ids
