"""Thin authenticated routes; formal save stays in the existing draft receipt path."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header

from app import imports, store
from app.contracts import ResourceView
from app.semester_calendar import preview_semester
from app.semester_contracts import SemesterRule, SemesterUndo


def semester_calendar_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/semester-calendars", response_model=list[ResourceView])
    async def listing(user=Depends(current_user), db=Depends(get_db)):
        rows = await store.rows(db, str(user.id), "semester_calendar_batch")
        undone = {r.data["undo_of"]: r.id for r in rows if r.data.get("undo_of")}
        return [
            {**store.view(r), "data": {**r.data, "undone_by": undone.get(r.id)}}
            for r in rows
        ]

    @router.post("/drafts/semester-calendar", response_model=ResourceView)
    async def draft(
        body: Annotated[SemesterRule | SemesterUndo, Body(discriminator="operation")],
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner, payload = str(user.id), body.model_dump(mode="json")

        async def op():
            review = await preview_semester(db, owner, payload)
            return await imports.create_draft(
                db,
                owner,
                "semester_calendar",
                payload,
                {"preview": review, "generated_hash": store.digest(payload)},
            )

        return await store.mutate(
            db, owner, "semester-calendar-draft", key, payload, op
        )

    return router
