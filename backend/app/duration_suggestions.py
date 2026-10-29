"""B-owned acceptance boundary. The caller owns one serialized transaction."""

from fastapi import HTTPException
from pydantic import ValidationError

from app import store
from app.db import Resource
from app.duration_suggestions_contracts import (
    DurationSuggestionData,
    DurationSuggestionView,
)
from app.planning_history import record_change


async def source_revision(db, owner):
    rows = await store.rows(db, owner, "settings")
    return rows[0].revision if rows else 0


async def owned_optional(db, owner, rid, kind):
    resource = await db.get(Resource, rid)
    return (
        resource
        if resource and resource.owner_id == owner and resource.kind == kind
        else None
    )


async def inspect(db, owner, resource, data):
    task = await owned_optional(db, owner, data.task_id, "task")
    step = await owned_optional(db, owner, data.step_id, "step")
    current_source = await source_revision(db, owner)
    expected_step = (
        data.applied_step_revision
        if data.state in {"accepted", "restored"}
        else data.step_revision
    )
    expected_source = (
        data.applied_source_revision
        if data.state in {"accepted", "restored"}
        else data.source_revision
    )
    reason = None
    if not task or not step or step.data.get("task_id") != data.task_id:
        reason = "关联任务或步骤不可用，或归属已变化"
    elif (
        task.revision != data.task_revision
        or step.revision != expected_step
        or current_source != expected_source
    ):
        reason = "任务、步骤或资料版本已变化"
    elif task.data.get("status") != "open" or step.data.get("status") != "open":
        reason = "任务或步骤已不是待完成状态"
    elif (
        data.state == "pending"
        and step.data.get("estimated_minutes") != data.default_estimated_minutes
    ):
        reason = "原预计时长与生成依据不一致"
    elif (
        data.state == "accepted"
        and step.data.get("estimated_minutes") != data.suggested_minutes
    ):
        reason = "已应用时长发生变化"
    elif (
        data.state == "restored"
        and step.data.get("estimated_minutes") != data.default_estimated_minutes
    ):
        reason = "默认时长发生变化"
    if reason is None:
        records = await store.rows(db, owner, "execution")
        superseded = {r.data.get("supersedes_id") for r in records}
        mapping = {r.id: r for r in records}
        for sample in data.sample_basis:
            record = mapping.get(sample.execution_id)
            if (
                not record
                or record.id in superseded
                or record.revision != sample.execution_revision
                or record.data.get("task_id") != data.task_id
                or record.data.get("step_id") != data.step_id
                or type(record.data.get("actual_minutes")) is not int
                or record.data.get("actual_minutes") != sample.actual_minutes
                or record.data.get("feedback") != sample.feedback
            ):
                reason = "执行样本已变化、被更正或缺少有效事实"
                break
    view = DurationSuggestionView(
        id=resource.id,
        revision=resource.revision,
        data=data,
        freshness="stale" if reason else "fresh",
        freshness_reason=reason,
        current_task_revision=task.revision if task else None,
        current_step_revision=step.revision if step else None,
        current_source_revision=current_source,
        current_estimated_minutes=step.data.get("estimated_minutes") if step else None,
        task_title=task.data.get("title") if task else None,
        step_title=step.data.get("title") if step else None,
    ).model_dump(mode="json")
    return view, task, step


async def list_suggestions(db, owner):
    suggestions, invalid = [], 0
    for resource in await store.rows(db, owner, "duration_suggestion"):
        try:
            data = DurationSuggestionData.model_validate(resource.data)
        except ValidationError:
            invalid += 1
            continue
        view, _, _ = await inspect(db, owner, resource, data)
        suggestions.append(view)
    return {
        "contract_version": "duration-suggestions-v1",
        "generation_status": "not_integrated",
        "source_revision": await source_revision(db, owner),
        "invalid_suggestion_count": invalid,
        "suggestions": suggestions,
    }


async def act(db, owner, rid, body, key):
    resource = await store.owned(db, owner, rid, "duration_suggestion")
    payload = body.model_dump(mode="json")
    scope = f"duration-suggestion-action:{rid}"
    # Historical exact retry precedes freshness checks; it can never reapply.
    receipt = await store.replay(db, owner, scope, key, payload)
    if receipt:
        return receipt.result
    try:
        data = DurationSuggestionData.model_validate(resource.data)
    except ValidationError as exc:
        raise HTTPException(409, "建议不符合时长消费契约，请等待有效生成结果") from exc
    store.revision(resource, body.revision)
    view, task, step = await inspect(db, owner, resource, data)
    if (
        view["freshness"] != "fresh"
        or body.task_revision != task.revision
        or body.step_revision != step.revision
        or body.source_revision != view["current_source_revision"]
    ):
        raise HTTPException(409, "建议依据已变化，请刷新后重新校对")
    if (body.action in {"accept", "reject"} and data.state != "pending") or (
        body.action == "restore_default" and data.state != "accepted"
    ):
        raise HTTPException(409, "当前建议状态不支持此操作")

    async def operation():
        updated = data.model_dump(mode="json")
        if body.action != "reject":
            minutes = (
                data.suggested_minutes
                if body.action == "accept"
                else data.default_estimated_minutes
            )
            step.data = {**step.data, "estimated_minutes": minutes}
            step.revision += 1
            await store.bump(db, owner)
            updated["applied_step_revision"] = step.revision
            updated["applied_source_revision"] = await source_revision(db, owner)
        updated["state"] = {
            "accept": "accepted",
            "reject": "rejected",
            "restore_default": "restored",
        }[body.action]
        resource.data = DurationSuggestionData.model_validate(updated).model_dump(
            mode="json"
        )
        resource.revision += 1
        await record_change(
            db,
            owner,
            "duration_suggestion_action",
            resource.id,
            resource.revision,
            {
                "action": body.action,
                "task_id": task.id,
                "step_id": step.id,
                "step_revision": step.revision,
                "source_revision": await source_revision(db, owner),
            },
        )
        await db.flush()
        result, _, _ = await inspect(
            db, owner, resource, DurationSuggestionData.model_validate(resource.data)
        )
        return {
            "suggestion": result,
            "step": store.view(step),
            "source_revision": await source_revision(db, owner),
        }

    return await store.mutate(db, owner, scope, key, payload, operation)
