from fastapi import APIRouter, Depends, Header

from app import execution_timers, store
from app.contracts import ResourceView
from app.timer_contracts import TimerAction, TimerStart


def timer_router(get_db, current_user, boot_id):
    router = APIRouter(prefix="/api")

    @router.get("/execution-timers", response_model=list[ResourceView])
    async def timers(user=Depends(current_user), db=Depends(get_db)):
        return await execution_timers.list_timers(db, str(user.id), boot_id)

    @router.post("/execution-timers", response_model=ResourceView)
    async def start(
        body: TimerStart,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "timer-start",
            key,
            body.model_dump(mode="json"),
            lambda: execution_timers.start_timer(db, owner, body, boot_id),
        )

    @router.post("/execution-timers/{rid}/actions", response_model=ResourceView)
    async def act(
        rid: str,
        body: TimerAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "timer-action:" + rid,
            key,
            body.model_dump(mode="json"),
            lambda: execution_timers.act(db, owner, rid, body, boot_id),
        )

    return router
