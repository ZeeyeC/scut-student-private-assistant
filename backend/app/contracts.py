from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Window(StrictModel):
    start: time
    end: time

    @model_validator(mode="after")
    def order(self):
        if self.end <= self.start:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class StudentSettings(StrictModel):
    timezone: str = "Asia/Shanghai"
    semester_name: str = ""
    week1_monday: date | None = None
    week_count: int = Field(default=20, ge=1, le=30)
    periods: dict[int, Window] = Field(default_factory=dict)
    study_windows: list[Window] = Field(
        default_factory=lambda: [
            Window(start="09:00", end="12:00"),
            Window(start="14:00", end="18:00"),
            Window(start="19:00", end="21:00"),
        ]
    )
    daily_limit_minutes: int = Field(default=180, ge=15, le=720)
    max_block_minutes: int = Field(default=60, ge=15, le=240)
    min_block_minutes: int = Field(default=15, ge=5, le=60)
    buffer_minutes: int = Field(default=10, ge=0, le=120)

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("请输入有效 IANA 时区") from exc
        if self.week1_monday and self.week1_monday.weekday() != 0:
            raise ValueError("学期第一周锚点必须为周一")
        if self.min_block_minutes > self.max_block_minutes:
            raise ValueError("最短时间块超过最长时间块")
        windows = sorted(self.study_windows, key=lambda w: w.start)
        if any(a.end > b.start for a, b in zip(windows, windows[1:])):
            raise ValueError("学习窗口不能重叠")
        if any(k < 1 or k > 30 for k in self.periods):
            raise ValueError("非法节次")
        return self


class SettingsUpdate(StrictModel):
    revision: int
    data: StudentSettings
    id: str | None = None
    kind: str | None = None


class ResourceView(StrictModel):
    id: str
    kind: str
    revision: int
    data: dict


class Course(StrictModel):
    source_key: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    teacher: str | None = None
    campus: str | None = None
    location: str | None = None
    weekday: int = Field(ge=1, le=7)
    weeks: list[int] = Field(min_length=1, max_length=30)
    periods: list[int] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def valid_meeting(self):
        if any(w < 1 or w > 30 for w in self.weeks + self.periods):
            raise ValueError("周次/节次范围为 1..30")
        self.weeks = sorted(set(self.weeks))
        self.periods = sorted(set(self.periods))
        return self


class Timetable(StrictModel):
    courses: list[Course] = Field(max_length=500)
    completeness: Literal["partial", "unknown", "full"] = "partial"
    semester_label: str = Field(max_length=200)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self):
        if len({c.source_key for c in self.courses}) != len(self.courses):
            raise ValueError("课程来源标识重复")
        return self


class Confirm(StrictModel):
    revision: int


class SchedulingConstraint(StrictModel):
    """First increment: an explicit, one-off protected interval for task planning."""

    title: str = Field(default="不可安排", min_length=1, max_length=200)
    strength: Literal["hard"] = "hard"
    recurrence: Literal["once"] = "once"
    timezone: str
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def valid_interval(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("请输入有效 IANA 时区") from exc
        if not self.title.strip():
            raise ValueError("请输入禁排名称")
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo:
            raise ValueError("禁排时间必须带时区")
        # Compare instants, including intervals spanning a daylight-saving fold.
        from datetime import timezone

        if self.ends_at.astimezone(timezone.utc) <= self.starts_at.astimezone(
            timezone.utc
        ):
            raise ValueError("禁排结束时间必须晚于开始时间")
        return self


class ConstraintDraft(StrictModel):
    constraint: SchedulingConstraint
    constraint_id: str | None = None
    constraint_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_target(self):
        if (self.constraint_id is None) != (self.constraint_revision is None):
            raise ValueError("修改禁排需要同时提供标识和版本")
        return self


class ConstraintStateUpdate(StrictModel):
    revision: int = Field(ge=1)
    active: bool


class DraftEdit(StrictModel):
    revision: int
    payload: dict


class CalendarException(StrictModel):
    course_id: str
    date: date
    cancelled: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None


class FixedEvent(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def check_times(self):
        if (
            not self.starts_at.tzinfo
            or not self.ends_at.tzinfo
            or self.ends_at <= self.starts_at
        ):
            raise ValueError("需要带时区且有序的时间")
        return self


class Evidence(StrictModel):
    field: str
    text: str


class AcademicDeadlineBasis(StrictModel):
    expression: str = Field(max_length=200)
    week1_monday: date
    timezone: str


class CalendarDeadlineBasis(StrictModel):
    kind: Literal["calendar_boundary"]
    expression: str = Field(max_length=200)
    reference_date: date | None = None
    timezone: str


class AssignmentCandidate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    course_id: str | None = None
    requirements: list[str] = Field(default_factory=list, max_length=50)
    due_at: datetime | None = Field(
        default=None,
        description="ISO 8601 datetime with explicit UTC offset or Z. If the source timezone or exact date/time is unknown, output null and add due_at to uncertain_fields.",
    )
    due_text: str | None = None
    deadline_basis: AcademicDeadlineBasis | CalendarDeadlineBasis | None = None
    submission_method: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    uncertain_fields: list[str] = Field(default_factory=list)
    priority: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def aware_due(self):
        if self.due_at and not self.due_at.tzinfo:
            raise ValueError("截止时间必须带时区")
        return self


class AssignmentExtraction(StrictModel):
    items: list[AssignmentCandidate] = Field(min_length=1, max_length=30)
    warnings: list[str] = Field(default_factory=list)
    asset_id: str | None = None


class AssignmentJobRequest(StrictModel):
    asset_id: str
    consent: Literal[True]
    reference_time: datetime | None = None

    @model_validator(mode="after")
    def aware_reference(self):
        if self.reference_time and not self.reference_time.tzinfo:
            raise ValueError("消息日期必须带时区")
        return self


class StepCandidate(StrictModel):
    key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    estimated_minutes: int = Field(ge=5, le=240)
    dependency_keys: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)


class StepProposal(StrictModel):
    steps: list[StepCandidate] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def dag(self):
        graph = {s.key: s.dependency_keys for s in self.steps}
        if len(graph) != len(self.steps):
            raise ValueError("步骤标识重复")
        visited = set()
        active = set()

        def visit(k):
            if k not in graph:
                raise ValueError("依赖不存在")
            if k in active:
                raise ValueError("依赖有环")
            if k in visited:
                return
            active.add(k)
            for dep in graph[k]:
                visit(dep)
            active.remove(k)
            visited.add(k)

        for key in graph:
            visit(key)
        return self


class Decomposition(StepProposal):
    task_id: str
    task_revision: int


class StepDraftRequest(StepProposal):
    task_revision: int


class StepUpdate(StrictModel):
    revision: int
    spent_minutes: int | None = Field(default=None, ge=0, le=100000)
    estimated_minutes: int | None = Field(default=None, ge=5, le=240)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["open", "completed"] | None = None

    @model_validator(mode="after")
    def non_null_patch(self):
        for field in self.model_fields_set - {"revision"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能为空")
        return self


class TaskUpdate(StrictModel):
    revision: int
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["open", "completed", "archived"] | None = None
    due_at: datetime | None = None
    remedy_due_at: datetime | None = None
    priority: int | None = Field(default=None, ge=1, le=3)

    @model_validator(mode="after")
    def aware(self):
        for field in self.model_fields_set & {"title", "status", "priority"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能为空")
        for value in (self.due_at, self.remedy_due_at):
            if value and not value.tzinfo:
                raise ValueError("时间必须带时区")
        return self
