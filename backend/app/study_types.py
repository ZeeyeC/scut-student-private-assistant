"""Explicit target classifications; importing/OCR never invents or resets them."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field

from app import store
from app.contracts import StrictModel
from app.db import Resource, now
from app.planning_history import record_change

CourseType = Literal["unknown", "lecture", "lab", "seminar", "exam", "other"]
TaskType = Literal["unknown", "any", "deep", "review", "exercise", "other"]
Difficulty = Literal["unknown", "low", "medium", "high"]


class TypeWrite(StrictModel):
    revision: int = Field(ge=0, strict=True)
    target_revision: int = Field(ge=1, strict=True)
    course_type: CourseType | None = None
    task_type: TaskType | None = None
    difficulty: Difficulty = "unknown"


def classification_id(owner, kind, rid):
    return str(uuid5(NAMESPACE_URL, f"study-classification:{owner}:{kind}:{rid}"))


async def classifications(db, owner):
    result = {"course": {}, "task": {}}
    for row in await store.rows(db, owner, "study_classification"):
        d = row.data
        target = await db.get(Resource, d["target_id"])
        if (
            target
            and target.owner_id == owner
            and target.kind == d["target_kind"]
            and d.get("confirmed")
        ):
            result[target.kind][target.id] = {
                **d,
                "id": row.id,
                "revision": row.revision,
            }
    return result


def work_type(inputs, task_id):
    return inputs.get("study_classifications", {}).get("task", {}).get(task_id, {})


async def read_types(db, owner):
    rows = {r.id: r for r in await store.rows(db, owner, "study_classification")}
    settings = await store.rows(db, owner, "settings")
    items = []
    for kind in ("course", "task"):
        for target in await store.rows(db, owner, kind):
            row = rows.get(classification_id(owner, kind, target.id))
            items.append(
                {
                    "target": store.view(target),
                    "classification": store.view(row) if row else None,
                }
            )
    return {"source_revision": settings[0].revision if settings else 0, "items": items}


async def write_type(db, owner, kind, rid, body):
    target = await store.owned(db, owner, rid, kind)
    store.revision(target, body.target_revision)
    if (
        kind == "course"
        and (body.task_type is not None or body.difficulty != "unknown")
    ) or (kind == "task" and body.course_type is not None):
        raise HTTPException(422, "课程只能设置课程类型，任务设置工作类型和难度")
    cid = classification_id(owner, kind, rid)
    row = await db.get(Resource, cid)
    if (row.revision if row else 0) != body.revision:
        raise HTTPException(409, "类型设置已变化，请刷新后核对")
    data = {
        "schema_version": 1,
        "target_id": rid,
        "target_kind": kind,
        "target_revision": target.revision,
        "source": "user",
        "confirmed": True,
        "updated_at": now().isoformat(),
        "course_type": body.course_type or "unknown",
        "task_type": body.task_type or "unknown",
        "difficulty": body.difficulty,
    }
    if row:
        row.data = {
            **data,
            "history": [
                *row.data.get("history", []),
                {k: v for k, v in row.data.items() if k != "history"},
            ],
        }
        row.revision += 1
    else:
        row = Resource(
            id=cid,
            owner_id=owner,
            kind="study_classification",
            data={**data, "history": []},
        )
        db.add(row)
    await db.flush()
    await store.bump(db, owner)
    await record_change(
        db,
        owner,
        "study_classification_changed",
        row.id,
        row.revision,
        {"target_id": rid, "target_kind": kind},
    )
    return store.view(row)


def study_type_router(get_db, current_user):
    router = APIRouter(prefix="/api/study-types")

    @router.get("")
    async def read(user=Depends(current_user), db=Depends(get_db)):
        return await read_types(db, str(user.id))

    @router.put("/{kind}/{rid}")
    async def save(
        kind: Literal["course", "task"],
        rid: str,
        body: TypeWrite,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            f"study-type:{kind}:{rid}",
            key,
            body.model_dump(mode="json"),
            lambda: write_type(db, owner, kind, rid, body),
        )

    return router
