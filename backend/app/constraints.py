"""Confirmed protected intervals reuse the existing draft and receipt transaction."""

from uuid import uuid4

from fastapi import APIRouter, Depends, Header

from app import imports, store
from app.contracts import ConstraintDraft, ConstraintStateUpdate, ResourceView
from app.db import Resource, now
from app.planning_history import record_change


def active_constraints(rows):
    return [r for r in rows if r["data"].get("active") and r["data"].get("confirmed")]


async def check_target(db, owner, payload):
    if payload["constraint_id"] is not None:
        r = await store.owned(
            db, owner, payload["constraint_id"], "scheduling_constraint"
        )
        store.revision(r, payload["constraint_revision"])
        return r
    return None


async def save_constraint(db, owner, draft, payload):
    r = await check_target(db, owner, payload)
    before = store.view(r) if r else None
    if r is None:
        r = Resource(id=str(uuid4()), owner_id=owner, kind="scheduling_constraint")
        r.revision = 1
        db.add(r)
        active = True
    else:
        active = r.data["active"]
        r.revision += 1
    r.data = {
        **payload["constraint"],
        "active": active,
        "confirmed": True,
        "source": {"kind": "manual", "draft_id": draft.id},
        "confirmed_at": now().isoformat(),
    }
    await db.flush()
    await record_change(
        db,
        owner,
        "constraint_changed",
        r.id,
        r.revision,
        {
            "before": before,
            "after": store.view(r),
        },
    )
    return [r.id]


def constraint_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/scheduling-constraints", response_model=list[ResourceView])
    async def listing(user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(r)
            for r in await store.rows(db, str(user.id), "scheduling_constraint")
        ]

    @router.post("/drafts/scheduling-constraint", response_model=ResourceView)
    async def draft(
        body: ConstraintDraft,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner, payload = str(user.id), body.model_dump(mode="json")

        async def op():
            await check_target(db, owner, payload)
            return await imports.create_draft(
                db, owner, "scheduling_constraint", payload
            )

        return await store.mutate(db, owner, "constraint-draft", key, payload, op)

    @router.patch("/scheduling-constraints/{rid}", response_model=ResourceView)
    async def state(
        rid: str,
        body: ConstraintStateUpdate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            r = await store.owned(db, owner, rid, "scheduling_constraint")
            store.revision(r, body.revision)
            if r.data["active"] != body.active:
                before = store.view(r)
                r.data = {**r.data, "active": body.active}
                r.revision += 1
                await store.bump(db, owner)
                await record_change(
                    db,
                    owner,
                    "constraint_changed",
                    r.id,
                    r.revision,
                    {
                        "before": before,
                        "after": store.view(r),
                    },
                )
            return store.view(r)

        return await store.mutate(
            db, owner, f"constraint-state:{rid}", key, body.model_dump(), op
        )

    return router
