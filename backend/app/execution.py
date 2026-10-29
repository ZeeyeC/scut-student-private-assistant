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


def covered_blocks(record):
    result = set(record.data.get("covered_plan_block_ids", []))
    if record.data.get("plan_block_id"):
        result.add(record.data["plan_block_id"])
    return result


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
        covered = set().union(*(covered_blocks(r) for r in actual)) if actual else set()
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
    actual_seconds = (
        sum(
            r.data.get("actual_seconds", r.data["actual_minutes"] * 60) for r in records
        )
        if records
        else None
    )
    actual_minutes = actual_seconds // 60 if actual_seconds is not None else None
    return ExecutionSummary(
        task_id=task_id,
        step_id=step_id,
        actual_minutes=actual_minutes,
        actual_seconds=actual_seconds,
        unconfirmed_execution_ids=[
            r.id for r in records if r.data.get("unconfirmed_interval")
        ],
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


async def prepare_execution(
    db, owner, body, *, persist_baseline=True, historical_timezone=False
):
    task = await store.owned(db, owner, body.task_id, "task")
    store.revision(task, body.task_revision)
    settings = await store.settings(db, owner)
    if not historical_timezone and body.timezone != settings.data["timezone"]:
        raise HTTPException(409, "时区设置已变化，请刷新后记录")
    if body.performed_on > now().astimezone(ZoneInfo(body.timezone)).date():
        raise HTTPException(422, "实际执行日期不能在未来")
    coverage, separate = [], []
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
                block.id in covered_blocks(r)
                for r in effective(await execution_history(db, owner, task.id))
            ):
                raise HTTPException(409, "该时间块已有反馈，请更正原记录")
        state = await baseline(db, owner, step, create=persist_baseline)
        step_blocks = [
            b.id
            for b in await store.rows(db, owner, "plan_block")
            if b.data.get("step_id") == step.id
        ]
        if not body.plan_block_id and (step_blocks or state.data["allocations"]):
            if body.legacy_resolution is None:
                raise HTTPException(
                    409, "请选择对应安排，或明确与当前全部安排及旧估算的覆盖关系"
                )
            coverage = (
                sorted(set(step_blocks) | set(state.data["allocations"]))
                if body.legacy_resolution == "replace"
                else []
            )
            separate = step_blocks if body.legacy_resolution == "separate" else []
            if any(
                set(coverage) & covered_blocks(r)
                for r in effective(await execution_history(db, owner, task.id))
            ):
                raise HTTPException(
                    409, "覆盖的安排已有实际记录，请更正原记录或选择另一段投入"
                )
        if (
            state.data["unallocated_minutes"]
            and state.data["unallocated_resolution"] is None
        ):
            if body.legacy_resolution is None:
                raise HTTPException(
                    409, "旧估算覆盖范围不明，请选择替代或作为另一段投入"
                )
            if persist_baseline:
                state.data = {
                    **state.data,
                    "unallocated_resolution": body.legacy_resolution,
                }
                state.revision += 1
    return task, coverage, separate


async def record_execution(
    db,
    owner: str,
    body: ExecutionWrite,
    *,
    source="manual",
    actual_seconds=None,
    timer_id=None,
) -> dict:
    task = await store.owned(db, owner, body.task_id, "task")
    payload = body.model_dump(mode="json")
    request_hash = store.digest(
        {
            "operation": "create",
            "body": payload,
            **(
                {
                    "source": source,
                    "actual_seconds": actual_seconds,
                    "timer_id": timer_id,
                }
                if source != "manual" or timer_id
                else {}
            ),
        }
    )
    replay = await replay_operation(db, owner, body.client_operation_id, request_hash)
    if replay:
        return replay
    rid = identity(owner, "fact", body.execution_id)
    if await db.get(Resource, rid):
        raise HTTPException(409, "该次执行已记录，请使用更正")
    # A timer's trusted saved target keeps the timezone observed at its start.
    # New direct manual writes still validate against the current settings.
    task, coverage, separate = await prepare_execution(
        db, owner, body, historical_timezone=timer_id is not None
    )
    if timer_id is None:
        for timer in await store.rows(db, owner, "execution_timer"):
            target = timer.data["target"]
            if (
                target.get("step_id") == body.step_id
                and target["task_id"] == body.task_id
                and timer.data["status"] not in ("finished", "discarded")
            ):
                raise HTTPException(
                    409, "此步骤有未结束计时，请先结束或在计时中改为补记"
                )
    record = Resource(
        id=rid,
        owner_id=owner,
        kind="execution",
        data={
            **payload,
            "schema_version": 1,
            "source": source,
            **(
                {"actual_seconds": actual_seconds} if actual_seconds is not None else {}
            ),
            **({"timer_id": timer_id} if timer_id else {}),
            "supersedes_id": None,
            "request_hash": request_hash,
            "recorded_at": now().isoformat(),
            "covered_plan_block_ids": coverage,
            "separate_plan_block_ids": separate,
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
            "source": "manual",
            "corrected_source": original.data.get("source", "manual"),
            "actual_seconds": body.actual_minutes * 60,
            "unconfirmed_interval": False,
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
    if total_minutes == summary.planning_spent_minutes:
        state.data = {**state.data, "history": history}
    else:
        records = effective(await execution_history(db, owner, task.id))
        covered = (
            set().union(*(covered_blocks(r) for r in records)) if records else set()
        )
        known = sum(
            n for bid, n in state.data["allocations"].items() if bid not in covered
        )
        allocations = (
            state.data["allocations"] if total_minutes - actual >= known else {}
        )
        remainder = total_minutes - actual - (known if allocations else 0)
        state.data = {
            **state.data,
            "allocations": allocations,
            "unallocated_minutes": remainder,
            "unallocated_resolution": None,
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
    active = [r for r in effective(history) if r.data.get("step_id") == step.id]
    has_actual = any(block.id in covered_blocks(r) for r in active)
    if not has_actual and any(
        not covered_blocks(r)
        and block.id not in r.data.get("separate_plan_block_ids", [])
        for r in active
    ):
        raise HTTPException(
            409,
            "已有未关联安排的实际投入，请先核对是否属于同一次执行，不能直接叠加估算",
        )
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
