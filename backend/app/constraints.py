"""Confirmed protected intervals reuse the existing draft and receipt transaction."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException

from app import imports, store
from app.contracts import (
    ConstraintDraft,
    ConstraintStateUpdate,
    DraftEdit,
    ResourceView,
)
from app.db import Resource, now
from app.planning_history import record_change


def active_constraints(rows):
    return [r for r in rows if r["data"].get("active") and r["data"].get("confirmed")]


def local_instant(value, zone):
    """Never choose a skipped or duplicated wall clock time for a user."""
    result = value.replace(tzinfo=zone, fold=0)
    if (
        result.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != value
        or result.utcoffset() != value.replace(tzinfo=zone, fold=1).utcoffset()
    ):
        raise ValueError(
            "重复禁排遇到夏令时缺失或重复时间，请修改时刻或改用明确的单次禁排"
        )
    return result


def expand_constraints(rows, lower, upper):
    """Bounded read-only occurrences; weekly IDs retain their resource reference.

    `starts_at` local date is the inclusive effective-from date. Its local time
    and the end's local time/day offset repeat on the selected weekdays.
    `valid_until` includes starts on that day, including an overnight tail.
    """
    result = []
    for row in active_constraints(rows):
        data = row["data"]
        a, b = (
            datetime.fromisoformat(data["starts_at"]),
            datetime.fromisoformat(data["ends_at"]),
        )
        if data.get("recurrence", "once") == "once":
            if a < upper and b > lower:
                result.append(row)
            continue
        zone = ZoneInfo(data["timezone"])
        a, b = a.astimezone(zone), b.astimezone(zone)
        day_offset = (b.date() - a.date()).days
        cursor = max(a.date(), lower.astimezone(zone).date() - timedelta(days=1))
        last = upper.astimezone(zone).date()
        if data.get("valid_until"):
            last = min(last, date.fromisoformat(data["valid_until"]))
        while cursor <= last:
            if cursor.isoweekday() in data["weekdays"]:
                starts = local_instant(
                    datetime.combine(cursor, a.time().replace(tzinfo=None)), zone
                )
                ends = local_instant(
                    datetime.combine(
                        cursor + timedelta(days=day_offset),
                        b.time().replace(tzinfo=None),
                    ),
                    zone,
                )
                if starts.astimezone(timezone.utc) < upper.astimezone(
                    timezone.utc
                ) and ends.astimezone(timezone.utc) > lower.astimezone(timezone.utc):
                    result.append(
                        {
                            **row,
                            "id": f"{row['id']}:{cursor}",
                            "constraint_id": row["id"],
                            "occurrence_date": cursor.isoformat(),
                            "data": {
                                **data,
                                "starts_at": starts.isoformat(),
                                "ends_at": ends.isoformat(),
                            },
                        }
                    )
            cursor += timedelta(days=1)
    return sorted(
        result, key=lambda r: (datetime.fromisoformat(r["data"]["starts_at"]), r["id"])
    )


def planning_constraints(p, strength="hard"):
    zone = ZoneInfo(p["settings"]["timezone"])
    first = datetime.combine(date.fromisoformat(p["target_date"]), time.min, zone)
    last = first + timedelta(days=p["horizon_days"])
    # Revalidate preserved future/locked blocks outside the planning horizon too.
    starts = [first] + [
        datetime.fromisoformat(b["starts_at"]) for b in p["preserved_blocks"]
    ]
    ends = [last] + [
        datetime.fromisoformat(b["ends_at"]) for b in p["preserved_blocks"]
    ]
    return expand_constraints(
        [
            r
            for r in p.get("constraints", [])
            if r["data"].get("strength", "hard") == strength
        ],
        min(starts),
        max(ends),
    )


async def check_target(db, owner, payload):
    if payload["constraint_id"] is not None:
        r = await store.owned(
            db, owner, payload["constraint_id"], "scheduling_constraint"
        )
        store.revision(r, payload["constraint_revision"])
        return r
    return None


async def save_constraint(db, owner, draft, payload):
    r = await check_target(db, owner, payload)
    before = store.view(r) if r else None
    if r is None:
        r = Resource(id=str(uuid4()), owner_id=owner, kind="scheduling_constraint")
        r.revision = 1
        db.add(r)
        active = True
    else:
        active = r.data["active"]
        r.revision += 1
    r.data = {
        **payload["constraint"],
        "active": active,
        "confirmed": True,
        "source": {"kind": "manual", "draft_id": draft.id},
        "confirmed_at": now().isoformat(),
    }
    await db.flush()
    await record_change(
        db,
        owner,
        "constraint_changed",
        r.id,
        r.revision,
        {
            "before": before,
            "after": store.view(r),
        },
    )
    return [r.id]


def constraint_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.post("/drafts/{rid}/constraint-preview")
    async def preview(
        rid: str,
        body: DraftEdit,
        start: date,
        end: date,
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        if end < start or (end - start).days > 366:
            raise HTTPException(422, "预览日期范围应在一年内")
        owner = str(user.id)
        draft = await store.owned(db, owner, rid, "draft")
        store.revision(draft, body.revision)
        if (
            draft.data["draft_kind"] != "scheduling_constraint"
            or draft.data["status"] != "pending"
        ):
            raise HTTPException(409, "请选择尚未保存的禁排草稿")
        payload = imports.validate_payload("scheduling_constraint", body.payload)
        if any(
            payload[k] != draft.data["payload"][k]
            for k in ("constraint_id", "constraint_revision")
        ):
            raise HTTPException(422, "草稿目标不能改变，请重新创建")
        target = await check_target(db, owner, payload)
        zone = ZoneInfo(payload["constraint"]["timezone"])
        lower, upper = (
            datetime.combine(start, time.min, zone),
            datetime.combine(end + timedelta(days=1), time.min, zone),
        )
        try:
            windows = expand_constraints(
                [
                    {
                        "id": target.id if target else draft.id,
                        "kind": "scheduling_constraint",
                        "revision": target.revision if target else 1,
                        "data": {
                            **payload["constraint"],
                            "active": True,
                            "confirmed": True,
                        },
                    }
                ],
                lower,
                upper,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        affected = [
            store.view(b)
            for b in await store.rows(db, owner, "plan_block")
            if payload["constraint"].get("strength", "hard") == "hard"
            and b.data["status"] != "completed"
            and any(
                datetime.fromisoformat(b.data["starts_at"])
                < datetime.fromisoformat(w["data"]["ends_at"])
                and datetime.fromisoformat(b.data["ends_at"])
                > datetime.fromisoformat(w["data"]["starts_at"])
                for w in windows
            )
        ]
        return {
            "start": start,
            "end": end,
            "timezone": payload["constraint"]["timezone"],
            "windows": windows,
            "affected_plans": affected,
            "active_after_save": target.data["active"] if target else True,
            "message": "预览不会写入禁排或改动已有安排；已停用的规则修改后仍停用。",
        }

    @router.get("/scheduling-constraints", response_model=list[ResourceView])
    async def listing(user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(r)
            for r in await store.rows(db, str(user.id), "scheduling_constraint")
        ]

    @router.post("/drafts/scheduling-constraint", response_model=ResourceView)
    async def draft(
        body: ConstraintDraft,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner, payload = str(user.id), body.model_dump(mode="json")

        async def op():
            await check_target(db, owner, payload)
            return await imports.create_draft(
                db, owner, "scheduling_constraint", payload
            )

        return await store.mutate(db, owner, "constraint-draft", key, payload, op)

    @router.patch("/scheduling-constraints/{rid}", response_model=ResourceView)
    async def state(
        rid: str,
        body: ConstraintStateUpdate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            r = await store.owned(db, owner, rid, "scheduling_constraint")
            store.revision(r, body.revision)
            if r.data["active"] != body.active:
                before = store.view(r)
                r.data = {**r.data, "active": body.active}
                r.revision += 1
                await store.bump(db, owner)
                await record_change(
                    db,
                    owner,
                    "constraint_changed",
                    r.id,
                    r.revision,
                    {
                        "before": before,
                        "after": store.view(r),
                    },
                )
            return store.view(r)

        return await store.mutate(
            db, owner, f"constraint-state:{rid}", key, body.model_dump(), op
        )

    return router
