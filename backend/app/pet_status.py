"""Small owner-scoped status projection, independent of the current UI page."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.contracts import StrictModel
from app.db import Resource


class PetStatus(StrictModel):
    state: Literal["idle", "thinking", "replying", "approval"]
    review_thread_id: str | None = None


async def pet_status(db, owner):
    active = list(
        (
            await db.scalars(
                select(Resource)
                .where(
                    Resource.owner_id == owner,
                    Resource.kind == "agent_run",
                    Resource.data["status"]
                    .as_string()
                    .in_(["queued", "running", "resume_queued", "waiting_approval"]),
                )
                .order_by(Resource.created_at, Resource.id)
            )
        ).all()
    )
    waiting = next(
        (run for run in active if run.data["status"] == "waiting_approval"), None
    )
    if waiting:
        return PetStatus(state="approval", review_thread_id=waiting.data["thread_id"])
    draft = await db.scalar(
        select(Resource.id)
        .where(
            Resource.owner_id == owner,
            Resource.kind == "draft",
            Resource.data["status"].as_string() == "pending",
        )
        .limit(1)
    )
    if draft:
        return PetStatus(state="approval")
    if active:
        return PetStatus(
            state="replying"
            if any(
                run.data.get("pet_phase") == "replying"
                and run.data["status"] == "running"
                for run in active
            )
            else "thinking"
        )
    return PetStatus(state="idle")


def pet_router(get_db, current_user):
    router = APIRouter(prefix="/api/agent")

    @router.get("/pet-state", response_model=PetStatus)
    async def status(user=Depends(current_user), db=Depends(get_db)):
        return await pet_status(db, str(user.id))

    return router
