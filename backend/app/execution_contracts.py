"""Version one execution facts. No planned duration is an actual observation."""

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from app.contracts import ResourceView, StrictModel

Feedback = Literal["partial", "completed", "not_started", "skipped"]
Reason = Literal[
    "interrupted", "insufficient_time", "unsuitable_schedule", "skipped", "other"
]


class ExecutionTarget(StrictModel):
    client_operation_id: str = Field(min_length=1, max_length=160)
    execution_id: str = Field(min_length=1, max_length=160)
    task_id: str = Field(min_length=1)
    task_revision: int = Field(ge=1)
    step_id: str | None = None
    step_revision: int | None = Field(default=None, ge=1)
    plan_block_id: str | None = None
    plan_block_revision: int | None = Field(default=None, ge=1)
    performed_on: date
    timezone: str
    legacy_resolution: Literal["replace", "separate"] | None = None

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("需要有效 IANA 时区") from exc
        if (self.step_id is None) != (self.step_revision is None):
            raise ValueError("步骤及其版本必须同时提供")
        if (self.plan_block_id is None) != (self.plan_block_revision is None):
            raise ValueError("时间块及其版本必须同时提供")
        if self.plan_block_id and not self.step_id:
            raise ValueError("时间块必须关联步骤")
        return self


class ExecutionWrite(ExecutionTarget):
    actual_minutes: int = Field(ge=0, le=100000, strict=True)
    feedback: Feedback
    unfinished_reason: Reason | None = None
    task_status: Literal["open", "completed"] | None = None

    @model_validator(mode="after")
    def feedback_valid(self):
        if self.feedback in ("not_started", "skipped") and self.actual_minutes:
            raise ValueError("未执行或跳过的实际分钟必须为0")
        return self


class ExecutionCorrection(StrictModel):
    client_operation_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    task_revision: int = Field(ge=1)
    actual_minutes: int = Field(ge=0, le=100000, strict=True)
    feedback: Feedback
    unfinished_reason: Reason | None = None
    task_status: Literal["open", "completed"] | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.feedback in ("not_started", "skipped") and self.actual_minutes:
            raise ValueError("未执行或跳过的实际分钟必须为0")
        return self


class ExecutionView(ResourceView):
    pass


class ExecutionSummary(StrictModel):
    task_id: str
    step_id: str | None = None
    actual_minutes: int | None = None
    actual_seconds: int | None = None
    unconfirmed_execution_ids: list[str] = Field(default_factory=list)
    legacy_estimated_minutes: int = 0
    unresolved_legacy_minutes: int = 0
    planning_spent_minutes: int = 0
    unknown_step_ids: list[str] = Field(default_factory=list)
    effective_record_ids: list[str] = Field(default_factory=list)
    source_revision: int
