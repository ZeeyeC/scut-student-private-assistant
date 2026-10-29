from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException

from app import imports, store
from app.calendar import expand_calendar
from app.contracts import (
    CalendarException,
    Confirm,
    DraftConfirm,
    DraftEdit,
    FixedEvent,
    ResourceView,
    Timetable,
)
from app.db import Resource
from app.deletion import delete_draft
from app.schedule import calendar_events


def business_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/calendar-events")
    async def schedule(
        start: date, end: date, user=Depends(current_user), db=Depends(get_db)
    ):
        return await calendar_events(db, str(user.id), start, end)

    @router.post("/drafts/calendar-event", response_model=ResourceView)
    async def event_draft(
        body: FixedEvent,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await imports.create_draft(
                db, str(user.id), "calendar_event", body.model_dump(mode="json")
            )

        return await store.mutate(
            db,
            str(user.id),
            "calendar-event-draft",
            key,
            body.model_dump(mode="json"),
            op,
        )

    @router.get("/courses", response_model=list[ResourceView])
    async def courses(user=Depends(current_user), db=Depends(get_db)):
        return [store.view(r) for r in await store.rows(db, str(user.id), "course")]

    @router.get("/occurrences")
    async def occurrences(
        start: date, end: date, user=Depends(current_user), db=Depends(get_db)
    ):
        if end < start or (end - start).days > 366:
            raise HTTPException(422, "日期范围应在一年内")
        s = await store.settings(db, str(user.id))
        try:
            return expand_calendar(
                s.data,
                [store.view(r) for r in await store.rows(db, str(user.id), "course")],
                [r.data for r in await store.rows(db, str(user.id), "exception")],
                start,
                end,
            )
        except ValueError as e:
            raise HTTPException(422, str(e))

    @router.post("/drafts/timetable", response_model=ResourceView)
    async def timetable(
        body: Timetable,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await imports.create_draft(
                db, str(user.id), "timetable", body.model_dump(mode="json")
            )

        return await store.mutate(
            db, str(user.id), "timetable-draft", key, body.model_dump(mode="json"), op
        )

    @router.get("/drafts", response_model=list[ResourceView])
    async def drafts(user=Depends(current_user), db=Depends(get_db)):
        return [
            await imports.review_view(db, str(user.id), r)
            for r in await store.rows(db, str(user.id), "draft")
            if r.data["status"] == "pending"
        ]

    @router.get("/drafts/{rid}", response_model=ResourceView)
    async def draft(rid: str, user=Depends(current_user), db=Depends(get_db)):
        return await imports.review_view(
            db, str(user.id), await store.owned(db, str(user.id), rid, "draft")
        )

    @router.put("/drafts/{rid}", response_model=ResourceView)
    async def edit_draft(
        rid: str,
        body: DraftEdit,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await imports.edit_draft(
                db, str(user.id), rid, body.revision, body.payload
            )

        return await store.mutate(
            db, str(user.id), f"draft-edit:{rid}", key, body.model_dump(mode="json"), op
        )

    @router.delete("/drafts/{rid}")
    async def remove_draft(
        rid: str,
        body: Confirm,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await delete_draft(db, str(user.id), rid, body.revision)

        return await store.mutate(
            db, str(user.id), f"draft-delete:{rid}", key, body.model_dump(), op
        )

    @router.post("/drafts/{rid}/confirm")
    async def confirm(
        rid: str,
        body: DraftConfirm,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await imports.commit_draft(db, str(user.id), rid, body.revision, body.conflict_token)

        return await store.mutate(
            db, str(user.id), f"confirm:{rid}", key, body.model_dump(exclude_none=True), op
        )

    @router.post("/drafts/{rid}/conflict-preview")
    async def conflict_preview(
        rid: str, body: DraftEdit, user=Depends(current_user), db=Depends(get_db)
    ):
        from app.conflicts import draft_conflicts

        owner = str(user.id)
        draft = await store.owned(db, owner, rid, "draft")
        store.revision(draft, body.revision)
        return await draft_conflicts(db, owner, draft, body.payload)

    @router.post("/fixed-events", response_model=ResourceView)
    async def fixed(
        body: FixedEvent,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            r = Resource(
                owner_id=str(user.id),
                kind="fixed_event",
                data=body.model_dump(mode="json"),
            )
            db.add(r)
            await store.bump(db, str(user.id))
            await db.flush()
            return store.view(r)

        return await store.mutate(
            db, str(user.id), "fixed-event", key, body.model_dump(mode="json"), op
        )

    @router.get("/fixed-events", response_model=list[ResourceView])
    async def fixed_list(user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(r) for r in await store.rows(db, str(user.id), "fixed_event")
        ]

    @router.delete("/fixed-events/{rid}")
    async def fixed_delete(
        rid: str,
        body: Confirm,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            r = await store.owned(db, str(user.id), rid, "fixed_event")
            store.revision(r, body.revision)
            await db.delete(r)
            await store.bump(db, str(user.id))
            return {"deleted": True}

        return await store.mutate(
            db, str(user.id), f"fixed-delete:{rid}", key, body.model_dump(), op
        )

    @router.post("/calendar-exceptions", response_model=ResourceView)
    async def exception(
        body: CalendarException,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        await store.owned(db, str(user.id), body.course_id, "course")
        if bool(body.starts_at) != bool(body.ends_at):
            raise HTTPException(422, "补课需要起止时间")
        if body.starts_at and (
            not body.starts_at.tzinfo
            or not body.ends_at.tzinfo
            or body.ends_at <= body.starts_at
        ):
            raise HTTPException(422, "时间必须带时区且有序")

        async def op():
            r = Resource(
                owner_id=str(user.id),
                kind="exception",
                data=body.model_dump(mode="json"),
            )
            db.add(r)
            await store.bump(db, str(user.id))
            await db.flush()
            return store.view(r)

        return await store.mutate(
            db, str(user.id), "exception", key, body.model_dump(mode="json"), op
        )

    return router
