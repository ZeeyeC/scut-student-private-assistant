"""Explicit user review endpoints. No content-bearing mutation receipts."""

from fastapi import APIRouter, Depends, Header

from app import memories, store
from app.memory_contracts import (
    MemoryAction,
    MemoryPreferencesWrite,
    MemoryProposal,
    MemoryReset,
)


def memory_router(config, get_db, current_user):
    router = APIRouter(prefix="/api/memories")

    @router.get("")
    async def read(user=Depends(current_user), db=Depends(get_db)):
        return await memories.view(db, str(user.id))

    @router.post("/candidates")
    async def propose(
        body: MemoryProposal,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "memory-propose",
            key,
            body.model_dump(mode="json"),
            lambda: memories.propose(
                db,
                owner,
                body,
                {"kind": "user_ui", "explicit": True},
                (config.model_api_key,),
            ),
        )

    @router.post("/{rid}/forget")
    async def forget(
        rid: str,
        body: MemoryAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "memory-forget:" + rid,
            key,
            body.model_dump(),
            lambda: memories.propose_forget(
                db, owner, rid, body.revision, {"kind": "user_ui", "explicit": True}
            ),
        )

    @router.post("/candidates/{rid}/{action}")
    async def review(
        rid: str,
        action: str,
        body: MemoryAction,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        from fastapi import HTTPException

        operation = {
            "confirm": memories.confirm_candidate,
            "reject": memories.reject_candidate,
            "refresh": memories.refresh_candidate,
        }.get(action)
        if not operation:
            raise HTTPException(404, "操作不存在")
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "memory-" + action + ":" + rid,
            key,
            body.model_dump(),
            lambda: operation(db, owner, rid, body.revision),
        )

    @router.put("/preferences")
    async def preferences(
        body: MemoryPreferencesWrite,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "memory-preferences",
            key,
            body.model_dump(),
            lambda: memories.write_preferences(db, owner, body),
        )

    @router.post("/clear")
    async def clear(
        body: MemoryReset,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "memory-clear",
            key,
            body.model_dump(),
            lambda: memories.clear_memories(db, owner, body.revision),
        )

    return router
