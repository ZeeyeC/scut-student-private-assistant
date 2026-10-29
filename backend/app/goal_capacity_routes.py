"""Read-only shared goal capacity. Dependencies supply owner and transaction."""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.goal_capacity import read_goal_capacity


def goal_capacity_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/goal-capacity")
    async def read(
        week_start: date | None = None,
        timezone: str | None = None,
        expected_source_revision: int | None = Query(default=None, ge=0),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await read_goal_capacity(
            db, str(user.id), week_start, timezone, expected_source_revision
        )

    return router
