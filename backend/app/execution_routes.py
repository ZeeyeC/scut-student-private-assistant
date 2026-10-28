"""Thin execution endpoints using the existing request transaction and receipts."""

from fastapi import APIRouter, Depends, Header

from app import execution, store
from app.execution_contracts import (
    ExecutionCorrection,
    ExecutionSummary,
    ExecutionView,
    ExecutionWrite,
)


def execution_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.post("/executions", response_model=ExecutionView)
    async def record(
        body: ExecutionWrite,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "execution-create",
            key,
            body.model_dump(mode="json"),
            lambda: execution.record_execution(db, owner, body),
        )

    @router.post("/executions/{rid}/corrections", response_model=ExecutionView)
    async def correct(
        rid: str,
        body: ExecutionCorrection,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            f"execution-correct:{rid}",
            key,
            body.model_dump(mode="json"),
            lambda: execution.correct_execution(db, owner, rid, body),
        )

    @router.get("/tasks/{rid}/execution-summary", response_model=ExecutionSummary)
    async def summary(
        rid: str,
        step_id: str | None = None,
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await execution.execution_summary(db, str(user.id), rid, step_id)

    @router.get("/tasks/{rid}/executions", response_model=list[ExecutionView])
    async def history(rid: str, user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(r)
            for r in await execution.execution_history(db, str(user.id), rid)
        ]

    return router
