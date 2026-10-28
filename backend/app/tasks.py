from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text

from app import imports, store
from app.contracts import (
    Confirm,
    ResourceView,
    StepDraftRequest,
    StepProposal,
    StepUpdate,
    TaskUpdate,
)
from app.db import Resource
from app.deletion import delete_task


def validate_steps(steps):
    return StepProposal(steps=steps).model_dump(mode="json")["steps"]


async def apply_task_update(db, owner, rid, body: TaskUpdate):
    task = await store.owned(db, owner, rid, "task")
    store.revision(task, body.revision)
    patch = body.model_dump(mode="json", exclude_unset=True, exclude={"revision"})
    if "due_at" in patch:
        patch["deadline_basis"] = None
        uncertain = set(task.data.get("uncertain_fields", []))
        if patch["due_at"]:
            uncertain.discard("due_at")
            # A newly confirmed actual deadline supersedes an old recovery date.
            patch.setdefault("remedy_due_at", None)
        else:
            uncertain.add("due_at")
        patch["uncertain_fields"] = sorted(uncertain)
    task.data = {**task.data, **patch}
    task.revision += 1
    if {"due_at", "remedy_due_at"} & patch.keys():
        for draft in await store.rows(db, owner, "draft"):
            if draft.data["status"] != "pending":
                continue
            kind = draft.data["draft_kind"]
            if kind == "plan" or (
                kind == "decomposition" and draft.data["payload"]["task_id"] == rid
            ):
                draft.data = {
                    **draft.data,
                    "status": "superseded",
                    "invalidated_reason": "待办截止时间已更新，请重新生成",
                }
                draft.revision += 1
    await store.bump(db, owner)
    return store.view(task)


async def save_steps(db, owner, payload):
    t = await store.owned(db, owner, payload["task_id"], "task")
    store.revision(t, payload["task_revision"])
    old = [s for s in await store.rows(db, owner, "step") if s.data["task_id"] == t.id]
    recorded_steps = {
        r.data.get("step_id") for r in await store.rows(db, owner, "execution")
    }
    if any(s.id in recorded_steps and s.data["status"] != "completed" for s in old):
        raise HTTPException(409, "已有执行记录，请修改现有步骤，不能删除后重新拆解")
    blocks = await store.rows(db, owner, "plan_block")
    preserved_ids = {
        b.data["step_id"]
        for b in blocks
        if b.data.get("locked") or b.data.get("status") == "completed"
    }
    if any(s.id in preserved_ids and s.data["status"] != "completed" for s in old):
        raise HTTPException(409, "已有锁定安排，请先解锁再重新拆解")
    replaced = {s.id for s in old if s.data["status"] != "completed"}
    for block in blocks:
        if block.data["step_id"] in replaced:
            await db.delete(block)
    for s in old:
        if s.data["status"] != "completed":
            await db.delete(s)
    mapping = {s["key"]: str(uuid4()) for s in payload["steps"]}
    ids = []
    for step in payload["steps"]:
        r = Resource(
            id=mapping[step["key"]],
            owner_id=owner,
            kind="step",
            data={
                **step,
                "task_id": t.id,
                "dependency_ids": [mapping[k] for k in step["dependency_keys"]],
                "status": "open",
                "spent_minutes": 0,
            },
        )
        db.add(r)
        ids.append(r.id)
    t.revision += 1
    return ids


async def prepare_decomposition(db, owner, task_id, gateway):
    t = await store.owned(db, owner, task_id, "task")
    completed = [
        store.view(s)
        for s in await store.rows(db, owner, "step")
        if s.data["task_id"] == t.id and s.data["status"] == "completed"
    ]
    snapshot = store.view(t)
    settings = await store.settings(db, owner)
    source_revision = settings.revision
    await db.commit()
    result = await gateway.decompose_task(snapshot, completed)
    steps = validate_steps(result["steps"] if isinstance(result, dict) else result)
    await db.execute(text("BEGIN IMMEDIATE"))
    await db.refresh(t)
    store.revision(t, snapshot["revision"])
    await db.refresh(settings)
    store.revision(settings, source_revision)
    return {"task_id": t.id, "task_revision": t.revision, "steps": steps}


async def propose_decomposition(db, owner, task_id, gateway):
    payload = await prepare_decomposition(db, owner, task_id, gateway)
    return await imports.create_draft(
        db,
        owner,
        "decomposition",
        payload,
    )


def task_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/tasks/{rid}", response_model=ResourceView)
    async def task(rid: str, user=Depends(current_user), db=Depends(get_db)):
        return store.view(await store.owned(db, str(user.id), rid, "task"))

    @router.get("/tasks/{rid}/steps", response_model=list[ResourceView])
    async def steps(rid: str, user=Depends(current_user), db=Depends(get_db)):
        await store.owned(db, str(user.id), rid, "task")
        return [
            store.view(s)
            for s in await store.rows(db, str(user.id), "step")
            if s.data["task_id"] == rid
        ]

    @router.delete("/tasks/{rid}")
    async def remove_task(
        rid: str,
        body: Confirm,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await delete_task(db, str(user.id), rid, body.revision)

        return await store.mutate(
            db, str(user.id), f"task-delete:{rid}", key, body.model_dump(), op
        )

    @router.patch("/tasks/{rid}", response_model=ResourceView)
    async def update_task(
        rid: str,
        body: TaskUpdate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            return await apply_task_update(db, str(user.id), rid, body)

        return await store.mutate(
            db,
            str(user.id),
            f"task:{rid}",
            key,
            body.model_dump(mode="json", exclude_unset=True),
            op,
        )

    @router.patch("/steps/{rid}", response_model=ResourceView)
    async def update_step(
        rid: str,
        body: StepUpdate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def op():
            r = await store.owned(db, str(user.id), rid, "step")
            store.revision(r, body.revision)
            patch = body.model_dump(
                mode="json", exclude_unset=True, exclude={"revision"}
            )
            if "spent_minutes" in patch:
                from app.execution import apply_legacy_spent_update

                await apply_legacy_spent_update(
                    db, str(user.id), rid, body.revision, patch.pop("spent_minutes")
                )
            else:
                r.revision += 1
                await store.bump(db, str(user.id))
            r.data = {
                **r.data,
                **patch,
            }
            return store.view(r)

        return await store.mutate(
            db,
            str(user.id),
            f"step:{rid}",
            key,
            body.model_dump(mode="json", exclude_unset=True),
            op,
        )

    @router.post("/tasks/{rid}/step-drafts", response_model=ResourceView)
    async def draft_steps(
        rid: str,
        body: StepDraftRequest,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        t = await store.owned(db, str(user.id), rid, "task")
        store.revision(t, body.task_revision)

        async def op():
            return await imports.create_draft(
                db,
                str(user.id),
                "decomposition",
                {"task_id": rid, **body.model_dump(mode="json")},
            )

        return await store.mutate(
            db, str(user.id), f"step-draft:{rid}", key, body.model_dump(mode="json"), op
        )

    @router.post("/tasks/{rid}/decompose", response_model=ResourceView)
    async def decompose(
        rid: str,
        request: Request,
        body: dict,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        if body.get("consent") is not True:
            raise HTTPException(422, "需要确认向模型发送作业内容")
        receipt = await store.replay(db, str(user.id), f"decompose:{rid}", key, body)
        if receipt:
            return receipt.result
        try:
            payload = await prepare_decomposition(
                db, str(user.id), rid, request.app.state.gateway
            )
        except (ValueError, TimeoutError):
            raise HTTPException(503, "拆解失败或模型未配置，可以手工编辑步骤")

        async def op():
            return await imports.create_draft(
                db, str(user.id), "decomposition", payload
            )

        return await store.mutate(db, str(user.id), f"decompose:{rid}", key, body, op)

    return router
