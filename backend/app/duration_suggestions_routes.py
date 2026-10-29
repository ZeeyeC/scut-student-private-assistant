"""Consumption routes only; get_db provides an atomic serialized transaction."""

from fastapi import APIRouter, Depends, Header

from app import duration_suggestions
from app.duration_suggestions_contracts import (
    DurationAction,
    DurationActionResult,
    DurationSuggestionList,
)


def duration_suggestions_router(get_db, current_user):
    router = APIRouter(prefix="/api/duration-suggestions")

    @router.get("", response_model=DurationSuggestionList)
    async def read(user=Depends(current_user), db=Depends(get_db)):
        return await duration_suggestions.list_suggestions(db, str(user.id))

    @router.post("/{rid}/actions", response_model=DurationActionResult)
    async def action(
        rid: str,
        body: DurationAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await duration_suggestions.act(db, str(user.id), rid, body, key)

    return router
