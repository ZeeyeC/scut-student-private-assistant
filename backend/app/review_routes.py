"""Weekly review endpoints; supplied dependency owns an atomic write transaction."""

from datetime import date

from fastapi import APIRouter, Depends, Header

from app import store, weekly_review
from app.review_contracts import ReviewAction, WeeklyReview


def review_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/weekly-review", response_model=WeeklyReview)
    async def read(
        week_start: date,
        timezone: str | None = None,
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await weekly_review.read_weekly_review(
            db, str(user.id), week_start, timezone
        )

    @router.post("/weekly-review/actions")
    async def action(
        body: ReviewAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "weekly-review-action",
            key,
            body.model_dump(mode="json"),
            lambda: weekly_review.save_review_action(db, owner, body),
        )

    return router
