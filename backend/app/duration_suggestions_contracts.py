"""Consumption contract for a future duration generator; never generates advice."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.contracts import ResourceView, StrictModel

Revision = Annotated[int, Field(ge=1, strict=True)]
Minutes = Annotated[int, Field(ge=5, le=240, strict=True)]


class DurationSample(StrictModel):
    execution_id: str = Field(min_length=1)
    execution_revision: Revision
    actual_minutes: int = Field(ge=0, le=100000, strict=True)
    feedback: Literal["partial", "completed", "not_started", "skipped"]


class DurationSuggestionData(StrictModel):
    schema_version: Literal[1] = 1
    source: Literal["duration_generator"]
    task_id: str = Field(min_length=1)
    task_revision: Revision
    step_id: str = Field(min_length=1)
    step_revision: Revision
    source_revision: Revision
    default_estimated_minutes: Minutes | None
    suggested_minutes: Minutes
    reasons: list[str] = Field(min_length=1, max_length=20)
    sample_basis: list[DurationSample] = Field(min_length=1, max_length=1000)
    state: Literal["pending", "accepted", "rejected", "restored"] = "pending"
    applied_step_revision: Revision | None = None
    applied_source_revision: Revision | None = None

    @model_validator(mode="after")
    def valid(self):
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("建议理由不能为空")
        ids = [sample.execution_id for sample in self.sample_basis]
        if len(set(ids)) != len(ids):
            raise ValueError("样本不能重复")
        applied = (
            self.applied_step_revision is not None
            and self.applied_source_revision is not None
        )
        if (self.state in {"accepted", "restored"}) != applied:
            raise ValueError("应用状态需要完整的应用版本依据")
        if self.state in {"pending", "rejected"} and (
            self.applied_step_revision is not None
            or self.applied_source_revision is not None
        ):
            raise ValueError("未应用建议不能有应用版本")
        return self


class DurationAction(StrictModel):
    revision: Revision
    task_revision: Revision
    step_revision: Revision
    source_revision: Revision
    action: Literal["accept", "reject", "restore_default"]


class DurationSuggestionView(StrictModel):
    id: str
    kind: Literal["duration_suggestion"] = "duration_suggestion"
    revision: Revision
    data: DurationSuggestionData
    freshness: Literal["fresh", "stale"]
    freshness_reason: str | None
    current_task_revision: int | None
    current_step_revision: int | None
    current_source_revision: int
    current_estimated_minutes: int | None
    task_title: str | None
    step_title: str | None


class DurationSuggestionList(StrictModel):
    contract_version: Literal["duration-suggestions-v1"] = "duration-suggestions-v1"
    generation_status: Literal["not_integrated", "ready"] = "ready"
    source_revision: int
    invalid_suggestion_count: int = 0
    suggestions: list[DurationSuggestionView]


class DurationActionResult(StrictModel):
    suggestion: DurationSuggestionView
    step: ResourceView
    source_revision: int
