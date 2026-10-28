from typing import Literal

from pydantic import Field, model_validator

from app.contracts import StrictModel
from app.execution_contracts import ExecutionTarget, Feedback, Reason


class TimerStart(ExecutionTarget):
    pass


class TimerAction(StrictModel):
    revision: int = Field(ge=1)
    client_operation_id: str = Field(min_length=1, max_length=160)
    action: Literal["heartbeat", "pause", "resume", "finish", "discard"]
    feedback: Feedback | None = None
    unfinished_reason: Reason | None = None
    task_status: Literal["open", "completed"] | None = None
    task_revision: int | None = Field(default=None, ge=1)
    actual_minutes: int | None = Field(default=None, ge=0, le=100000, strict=True)

    @model_validator(mode="after")
    def valid(self):
        if self.action == "finish" and self.feedback is None:
            raise ValueError("结束计时需要执行反馈")
        if self.action != "finish" and any(
            v is not None
            for v in (
                self.feedback,
                self.unfinished_reason,
                self.task_status,
                self.actual_minutes,
            )
        ):
            raise ValueError("只有结束时可记录反馈或改为补记")
        if self.task_status is not None and self.task_revision is None:
            raise ValueError("修改任务状态需要当前任务版本")
        return self
