"""Authenticated negotiation routes; receipts precede version validation."""

from fastapi import APIRouter, Depends, Header

from app import negotiation, store
from app.contracts import ResourceView, StrictModel
from app.negotiation_contracts import (
    IntentAction,
    IntentChoose,
    IntentCreate,
    IntentPatch,
)


class IntentChoiceView(StrictModel):
    intent: ResourceView
    draft: ResourceView


def negotiation_router(get_db, current_user):
    router = APIRouter(prefix="/api/planning-intents")

    @router.get("", response_model=list[ResourceView])
    async def read(user=Depends(current_user), db=Depends(get_db)):
        return await negotiation.read_intents(db, str(user.id))

    @router.post("", response_model=ResourceView)
    async def create(
        body: IntentCreate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "intent-create",
            key,
            body.model_dump(mode="json"),
            lambda: negotiation.create_intent(db, owner, body),
        )

    @router.patch("/{rid}", response_model=ResourceView)
    async def patch(
        rid: str,
        body: IntentPatch,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            f"intent-patch:{rid}",
            key,
            body.model_dump(mode="json"),
            lambda: negotiation.patch_intent(db, owner, rid, body),
        )

    @router.post("/{rid}/preview", response_model=ResourceView)
    async def preview(
        rid: str,
        body: IntentAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            f"intent-preview:{rid}",
            key,
            body.model_dump(mode="json"),
            lambda: negotiation.preview_intent(db, owner, rid, body),
        )

    @router.post("/{rid}/choose", response_model=IntentChoiceView)
    async def choose(
        rid: str,
        body: IntentChoose,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            f"intent-choose:{rid}",
            key,
            body.model_dump(mode="json"),
            lambda: negotiation.choose_intent(db, owner, rid, body),
        )

    @router.post("/{rid}/cancel", response_model=ResourceView)
    async def cancel(
        rid: str,
        body: IntentAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            f"intent-cancel:{rid}",
            key,
            body.model_dump(mode="json"),
            lambda: negotiation.cancel_intent(db, owner, rid, body),
        )

    return router
