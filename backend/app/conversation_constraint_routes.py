from fastapi import APIRouter, Depends, Header

from app import conversation_constraints as domain
from app import store
from app.conversation_constraint_contracts import (
    ConstraintIntentAction,
    ConstraintIntentCreate,
    ConstraintIntentPatch,
)


def conversation_constraint_router(get_db, current_user):
    router = APIRouter(prefix="/api/constraint-intents")

    @router.get("")
    async def listing(
        thread_id: str | None = None, user=Depends(current_user), db=Depends(get_db)
    ):
        return await domain.read_intents(db, str(user.id), thread_id)

    @router.get("/{rid}")
    async def read(rid: str, user=Depends(current_user), db=Depends(get_db)):
        row = await store.owned(db, str(user.id), rid, "constraint_intent")
        return await domain.view_intent(db, str(user.id), row)

    async def mutate(db, owner, scope, key, body, operation):
        return await store.mutate(
            db, owner, scope, key, body.model_dump(mode="json"), operation
        )

    @router.post("")
    async def create(
        body: ConstraintIntentCreate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await mutate(
            db,
            owner,
            "constraint-intent-create",
            key,
            body,
            lambda: domain.create_intent(db, owner, body),
        )

    @router.patch("/{rid}")
    async def patch(
        rid: str,
        body: ConstraintIntentPatch,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await mutate(
            db,
            owner,
            f"constraint-intent-patch:{rid}",
            key,
            body,
            lambda: domain.patch_intent(db, owner, rid, body),
        )

    @router.post("/{rid}/prepare")
    async def prepare(
        rid: str,
        body: ConstraintIntentAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await mutate(
            db,
            owner,
            f"constraint-intent-prepare:{rid}",
            key,
            body,
            lambda: domain.prepare_intent(db, owner, rid, body),
        )

    @router.post("/{rid}/cancel")
    async def cancel(
        rid: str,
        body: ConstraintIntentAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await mutate(
            db,
            owner,
            f"constraint-intent-cancel:{rid}",
            key,
            body,
            lambda: domain.cancel_intent(db, owner, rid, body),
        )

    return router
