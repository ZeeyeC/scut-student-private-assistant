"""Lease-bound voluntary timers; only explicitly finished observations become facts."""

import math
from time import monotonic as monotonic_seconds

from fastapi import HTTPException

from app import execution, store
from app.db import Resource, now
from app.execution_contracts import ExecutionWrite
from app.planning_history import record_change

LEASE_SECONDS = 120


def status(timer, boot_id):
    data = timer.data
    if data["status"] != "running":
        return data["status"]
    delta = monotonic_seconds() - data["_tick"]
    if data["_boot_id"] != boot_id or not 0 <= delta <= LEASE_SECONDS:
        return "interrupted"
    return "running"


def view(timer, boot_id):
    data = {k: v for k, v in timer.data.items() if not k.startswith("_")}
    data["status"] = status(timer, boot_id)
    data["confirmed_elapsed_seconds"] = math.floor(data["elapsed_seconds"])
    if data["status"] == "running":
        data["elapsed_seconds"] += monotonic_seconds() - timer.data["_tick"]
    data["elapsed_seconds"] = math.floor(data["elapsed_seconds"])
    data["connection_lease_seconds"] = LEASE_SECONDS
    return {**store.view(timer), "data": data}


async def list_timers(db, owner, boot_id):
    return [view(r, boot_id) for r in await store.rows(db, owner, "execution_timer")]


async def check_running(db, owner, boot_id, exclude=None):
    for row in await store.rows(db, owner, "execution_timer"):
        if row.id != exclude and status(row, boot_id) == "running":
            raise HTTPException(409, "已有正在运行的计时，请先暂停或结束")


async def start_timer(db, owner, body, boot_id):
    rid = execution.identity(owner, "timer", body.execution_id)
    payload = body.model_dump(mode="json")
    digest = store.digest(payload)
    old = await db.get(Resource, rid)
    if old:
        if old.owner_id != owner or old.data["_start_hash"] != digest:
            raise HTTPException(409, "该次计时已存在，请读取当前状态")
        return view(old, boot_id)
    if await db.get(Resource, execution.identity(owner, "fact", body.execution_id)):
        raise HTTPException(409, "该次执行已有记录，请更正现有事实")
    # Starting an observation must not replace any existing execution estimate.
    await execution.prepare_execution(db, owner, body, persist_baseline=False)
    await check_running(db, owner, boot_id)
    for row in await store.rows(db, owner, "execution_timer"):
        if (
            body.plan_block_id
            and row.data["target"].get("plan_block_id") == body.plan_block_id
            and row.data["status"] not in ("finished", "discarded")
        ):
            raise HTTPException(409, "此安排已有未结束计时")
    stamp = now().isoformat()
    timer = Resource(
        id=rid,
        owner_id=owner,
        kind="execution_timer",
        data={
            "schema_version": 1,
            "target": payload,
            "task_id": body.task_id,
            "step_id": body.step_id,
            "status": "running",
            "elapsed_seconds": 0.0,
            "started_at": stamp,
            "last_observed_at": stamp,
            "segments": [],
            "interval_started_at": stamp,
            "current_segment_seconds": 0.0,
            "unconfirmed_interval": False,
            "_boot_id": boot_id,
            "_tick": monotonic_seconds(),
            "_start_hash": digest,
        },
    )
    db.add(timer)
    await db.flush()
    await store.bump(db, owner)
    await record_change(
        db,
        owner,
        "execution_timer_changed",
        timer.id,
        timer.revision,
        {"task_id": body.task_id, "status": "running"},
    )
    return view(timer, boot_id)


def observe(data, timer, boot_id):
    current = status(timer, boot_id)
    if current == "running":
        delta = monotonic_seconds() - data["_tick"]
        data["elapsed_seconds"] += delta
        data["current_segment_seconds"] += delta
        data["last_observed_at"] = now().isoformat()
        data["_tick"] = monotonic_seconds()
    elif data["status"] == "running":
        data["status"] = "interrupted"
        data["unconfirmed_interval"] = True
    return current


def close_segment(data):
    if data.get("interval_started_at") is not None:
        data["segments"] = [
            *data["segments"],
            {
                "starts_at": data["interval_started_at"],
                "ends_at": data["last_observed_at"],
                "seconds": data["current_segment_seconds"],
            },
        ]
        data["interval_started_at"] = None
        data["current_segment_seconds"] = 0.0


async def act(db, owner, timer_id, body, boot_id):
    timer = await store.owned(db, owner, timer_id, "execution_timer")
    digest = store.digest(body.model_dump(mode="json"))
    data = dict(timer.data)
    if data.get("_last_operation_id") == body.client_operation_id:
        if data["_last_hash"] != digest:
            raise HTTPException(409, "同一操作不能用于不同内容")
        return data["_last_result"]
    store.revision(timer, body.revision)
    if data["status"] in ("finished", "discarded"):
        raise HTTPException(409, "计时已结束，请读取记录或进行更正")
    current = observe(data, timer, boot_id)
    if body.action == "heartbeat":
        if current not in ("running", "interrupted"):
            raise HTTPException(409, "当前计时未运行")
    elif body.action == "pause":
        close_segment(data)
        if current != "interrupted":
            data["status"] = "paused"
    elif body.action == "resume":
        if current == "running":
            raise HTTPException(409, "计时已经运行")
        await check_running(db, owner, boot_id, timer.id)
        close_segment(data)
        data.update(
            status="running",
            _boot_id=boot_id,
            _tick=monotonic_seconds(),
            interval_started_at=now().isoformat(),
            last_observed_at=now().isoformat(),
        )
    else:
        close_segment(data)
        data["status"] = "finished" if body.action == "finish" else "discarded"
    timer.data = data
    timer.revision += 1
    if body.action == "finish":
        target = dict(data["target"])
        task = await store.owned(db, owner, target["task_id"], "task")
        if body.task_status is not None:
            store.revision(task, body.task_revision)
        target["task_revision"] = task.revision
        if target.get("step_id"):
            target["step_revision"] = (
                await store.owned(db, owner, target["step_id"], "step")
            ).revision
        if target.get("plan_block_id"):
            target["plan_block_revision"] = (
                await store.owned(db, owner, target["plan_block_id"], "plan_block")
            ).revision
        seconds = math.floor(data["elapsed_seconds"])
        manual = body.actual_minutes is not None
        if not manual and seconds > 0 and body.feedback in ("not_started", "skipped"):
            raise HTTPException(422, "已有计时投入，若实际未执行，请改为补记0分钟")
        minutes = body.actual_minutes if manual else seconds // 60
        write = ExecutionWrite(
            **{
                **target,
                "client_operation_id": body.client_operation_id,
                "actual_minutes": minutes,
                "feedback": body.feedback,
                "unfinished_reason": body.unfinished_reason,
                "task_status": body.task_status,
            }
        )
        result = await execution.record_execution(
            db,
            owner,
            write,
            source="manual" if manual else "timer",
            actual_seconds=None if manual else seconds,
            timer_id=timer.id,
        )
        record = await store.owned(db, owner, result["id"], "execution")
        record.data = {
            **record.data,
            "unconfirmed_interval": False if manual else data["unconfirmed_interval"],
        }
        timer.data = {
            **timer.data,
            "execution_record_id": record.id,
            "finish_source": "manual" if manual else "timer",
        }
    elif body.action != "heartbeat" or current == "interrupted":
        await store.bump(db, owner)
    if body.action != "heartbeat" or current == "interrupted":
        await record_change(
            db,
            owner,
            "execution_timer_changed",
            timer.id,
            timer.revision,
            {"task_id": data["task_id"], "status": timer.data["status"]},
        )
    result = view(timer, boot_id)
    timer.data = {
        **timer.data,
        "_last_operation_id": body.client_operation_id,
        "_last_hash": digest,
        "_last_result": result,
    }
    return result
