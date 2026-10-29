"""Router factory. get_db owns an atomic, serialized request transaction."""

from fastapi import APIRouter, Depends, Header

from app import proactive, store
from app.proactive_contracts import (
    ProactiveAction,
    ProactiveActionResult,
    ProactiveList,
    ProactivePreferenceView,
    ProactivePreferenceWrite,
    ProactiveRefresh,
)


def proactive_router(get_db, current_user):
    router = APIRouter(prefix="/api/proactive")

    @router.get("/preferences", response_model=ProactivePreferenceView)
    async def preferences(user=Depends(current_user), db=Depends(get_db)):
        return await proactive.read_preferences(db, str(user.id))

    @router.put("/preferences", response_model=ProactivePreferenceView)
    async def save(
        body: ProactivePreferenceWrite,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "proactive-preferences",
            key,
            body.model_dump(mode="json"),
            lambda: proactive.write_preferences(db, owner, body),
        )

    @router.get("/suggestions", response_model=ProactiveList)
    async def suggestions(user=Depends(current_user), db=Depends(get_db)):
        return await proactive.list_suggestions(db, str(user.id))

    @router.post("/refresh", response_model=ProactiveList)
    async def refresh(
        body: ProactiveRefresh, user=Depends(current_user), db=Depends(get_db)
    ):
        # Reconciliation is inherently idempotent and must always use fresh A
        # facts. A receipt caching yesterday's refresh would break that rule.
        return await proactive.refresh_suggestions(db, str(user.id), body.app_active)

    @router.post("/suggestions/{rid}/actions", response_model=ProactiveActionResult)
    async def action(
        rid: str,
        body: ProactiveAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await proactive.act_on_suggestion(db, str(user.id), rid, body, key)

    return router
