"""User-confirmed goals, with no inferred capacity or scheduling output."""
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator
from app.contracts import StrictModel


class GoalSubtaskInput(StrictModel):
    id: str | None = Field(default=None, min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    status: Literal['open', 'completed'] = 'open'
    estimated_minutes: int = Field(ge=0, le=100000, strict=True)
    task_id: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError('请输入子任务名称')
        return value.strip()


class GoalValues(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=4000)
    deadline: datetime | None = None
    weekly_budget_minutes: int = Field(ge=0, le=10080, strict=True)
    priority: int = Field(ge=1, le=3, strict=True)
    load_category: Literal['study', 'exercise', 'other']
    allowed_adjustment: Literal['reduce', 'delay', 'ask']
    paused: bool = Field(default=False, strict=True)
    subtasks: list[GoalSubtaskInput] = Field(default_factory=list, max_length=200)

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError('请输入目标名称')
        return value.strip()

    @field_validator('deadline')
    @classmethod
    def aware_deadline(cls, value):
        if value and (not value.tzinfo or value.utcoffset() is None):
            raise ValueError('截止时间必须带时区；未知可留空')
        return value

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [s.id for s in self.subtasks if s.id]
        if len(ids) != len(set(ids)):
            raise ValueError('子任务标识不能重复')
        return self


class GoalCreate(GoalValues):
    revision: int = Field(default=0, ge=0, le=0, strict=True)

    @model_validator(mode='after')
    def new_ids(self):
        if any(s.id for s in self.subtasks):
            raise ValueError('新建子任务不能指定标识')
        return self


class GoalPatch(StrictModel):
    revision: int = Field(ge=1, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    deadline: datetime | None = None
    weekly_budget_minutes: int | None = Field(default=None, ge=0, le=10080, strict=True)
    priority: int | None = Field(default=None, ge=1, le=3, strict=True)
    load_category: Literal['study', 'exercise', 'other'] | None = None
    allowed_adjustment: Literal['reduce', 'delay', 'ask'] | None = None
    paused: bool | None = Field(default=None, strict=True)
    subtasks: list[GoalSubtaskInput] | None = Field(default=None, max_length=200)

    @model_validator(mode='after')
    def valid_patch(self):
        changes = self.model_fields_set - {'revision'}
        if not changes:
            raise ValueError('请提供要修改的字段')
        if any(getattr(self, k) is None for k in changes - {'deadline'}):
            raise ValueError('仅截止时间可以明确设为未知')
        # Validate the shared field rules before any mutation begins.
        if self.title is not None:
            GoalValues.title_not_blank(self.title)
        GoalValues.aware_deadline(self.deadline)
        if self.subtasks is not None:
            ids = [s.id for s in self.subtasks if s.id]
            if len(ids) != len(set(ids)):
                raise ValueError('子任务标识不能重复')
        return self


class GoalCompletion(StrictModel):
    subtask_id: str
    title: str
    estimated_minutes: int
    task_id: str | None
    completed_at: datetime
    goal_revision: int


class GoalData(GoalValues):
    schema_version: Literal[1] = 1
    source: Literal['user'] = 'user'
    confirmed: Literal[True] = True
    updated_at: datetime
    completion_history: list[GoalCompletion] = Field(default_factory=list)


class GoalCapacity(StrictModel):
    status: Literal['unknown'] = 'unknown'
    weekly_available_minutes: None = None
    integration_status: Literal['pending'] = 'pending'


class GoalReference(StrictModel):
    subtask_id: str
    task_id: str
    available: bool
    revision: int | None = None
    title: str | None = None
    status: str | None = None


class GoalView(StrictModel):
    id: str
    kind: Literal['goal'] = 'goal'
    revision: int
    source_revision: int
    contract_version: Literal['goals-v1'] = 'goals-v1'
    data: GoalData
    capacity: GoalCapacity = Field(default_factory=GoalCapacity)
    references: list[GoalReference] = Field(default_factory=list)
    arrangements: list[dict] = Field(default_factory=list)


class GoalsView(StrictModel):
    contract_version: Literal['goals-v1'] = 'goals-v1'
    source_revision: int
    capacity: GoalCapacity = Field(default_factory=GoalCapacity)
    goals: list[GoalView]
