"""Owner-scoped execution ledger and its legacy planning projection.

Actual facts are append-only. Callers supply the existing business transaction.
"""

from datetime import datetime
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import store
from app.db import Resource, now
from app.execution_contracts import (
    ExecutionCorrection,
    ExecutionSummary,
    ExecutionWrite,
)
from app.planning_history import record_change


def identity(owner, category, key):
    return str(uuid5(NAMESPACE_URL, f"execution:{owner}:{category}:{key}"))


def legacy_estimates(step, blocks):
    """Read-only attribution: never assign a short aggregate to guessed blocks."""
    total = int(step.data.get("spent_minutes", 0))
    estimates = []
    for block in blocks:
        data = block.data
        if data.get("step_id") != step.id or data.get("status") != "completed":
            continue
        if data.get("execution_record_id"):
            continue
        minutes = max(
            0,
            int(
                (
                    datetime.fromisoformat(data["ends_at"])
                    - datetime.fromisoformat(data["starts_at"])
                ).total_seconds()
                // 60
            ),
        )
        estimates.append({"plan_block_id": block.id, "minutes": minutes})
    assigned = sum(item["minutes"] for item in estimates)
    if assigned > total:
        estimates, assigned = [], 0
    if total > assigned:
        estimates.append({"plan_block_id": None, "minutes": total - assigned})
    return estimates


async def baseline(db, owner, step, *, create=False):
    rid = identity(owner, "baseline", step.id)
    existing = await db.get(Resource, rid)
    if existing:
        return existing
    values = legacy_estimates(step, await store.rows(db, owner, "plan_block"))
    result = Resource(
        id=rid,
        owner_id=owner,
        kind="execution_baseline",
        data={
            "schema_version": 1,
            "task_id": step.data["task_id"],
            "step_id": step.id,
            "allocations": {
                v["plan_block_id"]: v["minutes"] for v in values if v["plan_block_id"]
            },
            "unallocated_minutes": sum(
                v["minutes"] for v in values if not v["plan_block_id"]
            ),
            "unallocated_resolution": None,
            "history": [],
            "source": "legacy_estimate",
        },
    )
    if create:
        db.add(result)
        await db.flush()
    return result


def effective(records):
    superseded = {r.data.get("supersedes_id") for r in records}
    return [r for r in records if r.id not in superseded]


async def execution_history(db, owner, task_id):
    await store.owned(db, owner, task_id, "task")
    return [
        r
        for r in await store.rows(db, owner, "execution")
        if r.data["task_id"] == task_id
    ]


async def execution_summary(
    db, owner: str, task_id: str, step_id: str | None = None
) -> ExecutionSummary:
    await store.owned(db, owner, task_id, "task")
    if step_id:
        step = await store.owned(db, owner, step_id, "step")
        if step.data["task_id"] != task_id:
            raise HTTPException(422, "步骤不属于该任务")
    steps = [
        s
        for s in await store.rows(db, owner, "step")
        if s.data["task_id"] == task_id and (not step_id or s.id == step_id)
    ]
    records = effective(
        [
            r
            for r in await execution_history(db, owner, task_id)
            if not step_id or r.data.get("step_id") == step_id
        ]
    )
    legacy, unresolved = 0, 0
    unknown = []
    for step in steps:
        state = await baseline(db, owner, step)
        actual = [r for r in records if r.data.get("step_id") == step.id]
        covered = {r.data.get("plan_block_id") for r in actual}
        unallocated = state.data["unallocated_minutes"]
        if state.data.get("unallocated_resolution") == "replace":
            unallocated = 0
        unresolved += (
            unallocated if state.data.get("unallocated_resolution") is None else 0
        )
        legacy += unallocated + sum(
            n for bid, n in state.data["allocations"].items() if bid not in covered
        )
        if not actual:
            unknown.append(step.id)
    actual_minutes = sum(r.data["actual_minutes"] for r in records) if records else None
    return ExecutionSummary(
        task_id=task_id,
        step_id=step_id,
        actual_minutes=actual_minutes,
        legacy_estimated_minutes=legacy,
        unresolved_legacy_minutes=unresolved,
        planning_spent_minutes=(actual_minutes or 0) + legacy,
        unknown_step_ids=unknown,
        effective_record_ids=[r.id for r in records],
        source_revision=(await store.settings(db, owner)).revision,
    )


async def replay_operation(db, owner, operation_id, request_hash):
    matches = [
        r
        for r in await store.rows(db, owner, "execution")
        if r.data["client_operation_id"] == operation_id
    ]
    if not matches:
        return None
    record = matches[0]
    if record.data["request_hash"] != request_hash:
        raise HTTPException(409, "同一执行操作不能用于不同内容，请读取现有记录")
    return store.view(record)


async def effects(db, owner, task, record, task_status):
    if task_status is not None:
        task.data = {**task.data, "status": task_status}
    task.revision += 1
    data = record.data
    if data.get("plan_block_id"):
        block = await store.owned(db, owner, data["plan_block_id"], "plan_block")
        block.data = {
            **block.data,
            "status": "completed",
            "execution_record_id": record.id,
        }
        block.revision += 1
    await db.flush()
    if data.get("step_id"):
        step = await store.owned(db, owner, data["step_id"], "step")
        result = await execution_summary(db, owner, task.id, step.id)
        step.data = {**step.data, "spent_minutes": result.planning_spent_minutes}
        step.revision += 1
    await store.bump(db, owner)
    await record_change(
        db,
        owner,
        "execution_changed",
        record.id,
        record.revision,
        {
            "task_id": task.id,
            "step_id": data.get("step_id"),
            "plan_block_id": data.get("plan_block_id"),
            "execution_id": data["execution_id"],
            "record_id": record.id,
            "supersedes_id": data.get("supersedes_id"),
            "source_revision": (await store.settings(db, owner)).revision,
        },
    )
    return store.view(record)


async def record_execution(db, owner: str, body: ExecutionWrite) -> dict:
    task = await store.owned(db, owner, body.task_id, "task")
    payload = body.model_dump(mode="json")
    request_hash = store.digest({"operation": "create", "body": payload})
    replay = await replay_operation(db, owner, body.client_operation_id, request_hash)
    if replay:
        return replay
    rid = identity(owner, "fact", body.execution_id)
    if await db.get(Resource, rid):
        raise HTTPException(409, "该次执行已记录，请使用更正")
    store.revision(task, body.task_revision)
    settings = await store.settings(db, owner)
    if body.timezone != settings.data["timezone"]:
        raise HTTPException(409, "时区设置已变化，请刷新后记录")
    if body.performed_on > now().astimezone(ZoneInfo(body.timezone)).date():
        raise HTTPException(422, "实际执行日期不能在未来")
    if body.step_id:
        step = await store.owned(db, owner, body.step_id, "step")
        if step.data["task_id"] != task.id:
            raise HTTPException(422, "步骤不属于该任务")
        store.revision(step, body.step_revision)
        if body.plan_block_id:
            block = await store.owned(db, owner, body.plan_block_id, "plan_block")
            if block.data["task_id"] != task.id or block.data["step_id"] != step.id:
                raise HTTPException(422, "时间块与任务步骤不匹配")
            store.revision(block, body.plan_block_revision)
            if any(
                r.data.get("plan_block_id") == block.id
                for r in await execution_history(db, owner, task.id)
            ):
                raise HTTPException(409, "该时间块已有反馈，请更正原记录")
        state = await baseline(db, owner, step, create=True)
        if (
            state.data["unallocated_minutes"]
            and state.data["unallocated_resolution"] is None
        ):
            if body.legacy_resolution is None:
                raise HTTPException(
                    409, "旧估算覆盖范围不明，请选择替代或作为另一段投入"
                )
            state.data = {
                **state.data,
                "unallocated_resolution": body.legacy_resolution,
            }
            state.revision += 1
    record = Resource(
        id=rid,
        owner_id=owner,
        kind="execution",
        data={
            **payload,
            "schema_version": 1,
            "source": "manual",
            "supersedes_id": None,
            "request_hash": request_hash,
            "recorded_at": now().isoformat(),
        },
    )
    db.add(record)
    await db.flush()
    return await effects(db, owner, task, record, body.task_status)


async def correct_execution(
    db, owner: str, record_id: str, body: ExecutionCorrection
) -> dict:
    original = await store.owned(db, owner, record_id, "execution")
    task = await store.owned(db, owner, original.data["task_id"], "task")
    payload = body.model_dump(mode="json")
    request_hash = store.digest(
        {"operation": "correct", "record_id": record_id, "body": payload}
    )
    replay = await replay_operation(db, owner, body.client_operation_id, request_hash)
    if replay:
        return replay
    store.revision(original, body.revision)
    store.revision(task, body.task_revision)
    history = await execution_history(db, owner, task.id)
    if any(r.data.get("supersedes_id") == record_id for r in history):
        raise HTTPException(409, "该记录已有更正，请选择当前有效记录")
    record = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="execution",
        data={
            **original.data,
            **payload,
            "supersedes_id": record_id,
            "request_hash": request_hash,
            "recorded_at": now().isoformat(),
        },
    )
    db.add(record)
    await db.flush()
    return await effects(db, owner, task, record, body.task_status)


async def apply_legacy_spent_update(
    db, owner: str, step_id: str, expected_revision: int, total_minutes: int
) -> dict:
    """Compatibility total edit: extra minutes are estimates, never new actuals."""
    step = await store.owned(db, owner, step_id, "step")
    store.revision(step, expected_revision)
    task = await store.owned(db, owner, step.data["task_id"], "task")
    state = await baseline(db, owner, step, create=True)
    summary = await execution_summary(db, owner, task.id, step.id)
    actual = summary.actual_minutes or 0
    if total_minutes < actual:
        raise HTTPException(422, "总量不能小于已记录实际投入，请更正执行记录")
    history = [
        *state.data.get("history", []),
        {
            "recorded_at": now().isoformat(),
            "previous": dict(state.data, history=None),
            "total_minutes": total_minutes,
        },
    ]
    state.data = {
        **state.data,
        "allocations": {},
        "unallocated_minutes": total_minutes - actual,
        "unallocated_resolution": "separate"
        if summary.actual_minutes is not None
        else None,
        "history": history,
    }
    state.revision += 1
    step.data = {**step.data, "spent_minutes": total_minutes}
    step.revision += 1
    task.revision += 1
    await store.bump(db, owner)
    await record_change(
        db,
        owner,
        "execution_changed",
        state.id,
        state.revision,
        {
            "task_id": task.id,
            "step_id": step.id,
            "source": "legacy_estimate",
            "source_revision": (await store.settings(db, owner)).revision,
        },
    )
    return store.view(step)


async def record_legacy_block_completion(db, owner: str, block):
    """Called by A's old completion route before changing the block status."""
    step = await store.owned(db, owner, block.data["step_id"], "step")
    state = await baseline(db, owner, step, create=True)
    history = await execution_history(db, owner, block.data["task_id"])
    has_actual = any(r.data.get("plan_block_id") == block.id for r in history)
    if not has_actual:
        minutes = max(
            0,
            int(
                (
                    datetime.fromisoformat(block.data["ends_at"])
                    - datetime.fromisoformat(block.data["starts_at"])
                ).total_seconds()
                // 60
            ),
        )
        state.data = {
            **state.data,
            "allocations": {**state.data["allocations"], block.id: minutes},
        }
        state.revision += 1
        await record_change(
            db,
            owner,
            "execution_changed",
            state.id,
            state.revision,
            {
                "task_id": block.data["task_id"],
                "step_id": step.id,
                "plan_block_id": block.id,
                "source": "legacy_estimate",
            },
        )
    await db.flush()
    summary = await execution_summary(db, owner, block.data["task_id"], step.id)
    step.data = {**step.data, "spent_minutes": summary.planning_spent_minutes}
    step.revision += 1
