"""Conservative same-step observed-total suggestions, using B's typed consumer.

Three effective, positive manual/timer observations and a final completion
feedback are required. This estimates this step's total, not a learned habit or
the median length of its sessions. No model, cross-task or inferred samples.
"""

from math import ceil
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header
from pydantic import Field

from app import execution, store
from app.contracts import StrictModel
from app.db import Resource
from app.duration_suggestions import list_suggestions
from app.duration_suggestions_contracts import (
    DurationSuggestionData,
    DurationSuggestionList,
)

RULE = "same-step-observed-total-1"


class GenerateDurations(StrictModel):
    expected_source_revision: int = Field(ge=1)


class GenerationResult(StrictModel):
    rule: str = RULE
    created_ids: list[str]
    refreshed_ids: list[str] = Field(default_factory=list)
    skipped: list[dict]
    result: DurationSuggestionList


async def generate(db, owner, body, key):
    async def operation():
        settings = await store.settings(db, owner)
        store.revision(settings, body.expected_source_revision)
        steps = await store.rows(db, owner, "step")
        tasks = {t.id: t for t in await store.rows(db, owner, "task")}
        all_records = await store.rows(db, owner, "execution")
        effective = execution.effective(all_records)
        record_map = {r.id: r for r in all_records}

        def logical_stamp(record):
            seen = set()
            while (
                record.data.get("supersedes_id") in record_map and record.id not in seen
            ):
                seen.add(record.id)
                record = record_map[record.data["supersedes_id"]]
            return record.created_at, record.id

        previous = await store.rows(db, owner, "duration_suggestion")
        created, refreshed, skipped = [], [], []
        for step in steps:
            task = tasks.get(step.data["task_id"])
            if (
                not task
                or task.data["status"] != "open"
                or step.data["status"] != "open"
            ):
                continue
            records = sorted(
                [
                    r
                    for r in effective
                    if r.data.get("step_id") == step.id
                    and r.data.get("task_id") == task.id
                ],
                key=lambda r: (r.data.get("performed_on", ""), *logical_stamp(r)),
            )
            summary = await execution.execution_summary(db, owner, task.id, step.id)
            reason = None
            if len(records) < 3 or len(records) > 1000:
                reason = "需同一步骤至少3条、至多1000条有效执行事实；更正链只取尾记录"
            elif summary.unconfirmed_execution_ids or summary.legacy_estimated_minutes:
                reason = "含未确认区间或旧估算，不作为可靠时长样本"
            elif any(
                r.data.get("source") not in ("manual", "timer")
                or type(r.data.get("actual_minutes")) is not int
                or r.data["actual_minutes"] <= 0
                or r.data.get("feedback") not in ("partial", "completed")
                for r in records
            ):
                reason = (
                    "需正分钟的真实部分/完成反馈；未知、0、未开始和跳过不推断为耗时样本"
                )
            elif records[-1].data["feedback"] != "completed":
                reason = "尚无最后一次完成反馈，累计投入只是下界，不推荐总预计值"
            total = sum(
                r.data["actual_minutes"]
                for r in records
                if type(r.data.get("actual_minutes")) is int
            )
            suggested = ceil(total / 5) * 5
            if reason is None and not 5 <= suggested <= 240:
                reason = (
                    "观测总量超出5–240分钟消费范围，请人工拆分步骤；不静默截断异常值"
                )
            if reason is None and suggested == step.data.get("estimated_minutes"):
                reason = "观测总量与当前预计一致，无需建议"
            default = step.data.get("estimated_minutes")
            if default is not None and (
                type(default) is not int or not 5 <= default <= 240
            ):
                reason = "原预计值超出消费契约，请先人工校对步骤"
            if reason:
                skipped.append({"step_id": step.id, "reason": reason})
                continue
            samples = [
                {
                    "execution_id": r.id,
                    "execution_revision": r.revision,
                    "actual_minutes": r.data["actual_minutes"],
                    "feedback": r.data["feedback"],
                }
                for r in records
            ]
            # The evidence identity excludes unrelated global revision changes.
            # A rejected/accepted/restored basis never reappears on refresh.
            basis = store.digest({"rule": RULE, "step_id": step.id, "samples": samples})
            identity = str(uuid5(NAMESPACE_URL, f"duration:{owner}:{basis}"))
            existing = next((r for r in previous if r.id == identity), None)
            if existing:
                if (
                    existing.data["state"] == "pending"
                    and existing.data["default_estimated_minutes"] == default
                    and (
                        existing.data["source_revision"],
                        existing.data["task_revision"],
                        existing.data["step_revision"],
                    )
                    != (settings.revision, task.revision, step.revision)
                ):
                    existing.data = DurationSuggestionData.model_validate(
                        {
                            **existing.data,
                            "source_revision": settings.revision,
                            "task_revision": task.revision,
                            "step_revision": step.revision,
                        }
                    ).model_dump(mode="json")
                    existing.revision += 1
                    refreshed.append(existing.id)
                skipped.append(
                    {
                        "step_id": step.id,
                        "reason": "同一依据已生成，保留已有选择；待确认建议可刷新版本，已处理建议不重现",
                    }
                )
                continue
            data = DurationSuggestionData(
                source="duration_generator",
                task_id=task.id,
                task_revision=task.revision,
                step_id=step.id,
                step_revision=step.revision,
                source_revision=settings.revision,
                default_estimated_minutes=step.data.get("estimated_minutes"),
                suggested_minutes=suggested,
                reasons=[
                    f"同一步骤{len(records)}条有效执行累计{total}分钟，末次为完成反馈；预计总量按5分钟向上取整为{suggested}分钟",
                    f"规则 {RULE}；不是跨任务学习或单次会话中位数，接受只修改本步骤预计值",
                    "有效更正链只计一次；不使用计划分钟、旧估算或未确认区间；超过240分钟交人工拆分",
                ],
                sample_basis=samples,
            )
            db.add(
                Resource(
                    id=identity,
                    owner_id=owner,
                    kind="duration_suggestion",
                    data=data.model_dump(mode="json"),
                )
            )
            created.append(identity)
        await db.flush()
        return GenerationResult(
            created_ids=created,
            refreshed_ids=refreshed,
            skipped=skipped,
            result=await list_suggestions(db, owner),
        ).model_dump(mode="json")

    return await store.mutate(
        db, owner, "duration-generation", key, body.model_dump(), operation
    )


def generator_router(get_db, current_user):
    router = APIRouter(prefix="/api/duration-suggestions")

    @router.post("/generate", response_model=GenerationResult)
    async def create(
        body: GenerateDurations,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await generate(db, str(user.id), body, key)

    return router
