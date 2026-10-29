"""Silent in-app suggestions; notification preferences are never planner rules."""

from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from app.contracts import ResourceView, StrictModel

Category = Literal[
    "deadline", "capacity", "unknown_estimate", "available_window", "facts_changed"
]
CATEGORIES = (
    "deadline",
    "capacity",
    "unknown_estimate",
    "available_window",
    "facts_changed",
)


class QuietWindow(StrictModel):
    weekdays: list[Annotated[int, Field(strict=True)]] = Field(
        min_length=1, max_length=7
    )
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def valid(self):
        if any(type(d) is not int or not 1 <= d <= 7 for d in self.weekdays):
            raise ValueError("星期需为1至7的整数")
        if len(set(self.weekdays)) != len(self.weekdays) or self.start == self.end:
            raise ValueError("星期不能重复；安静时段起止不能相同")
        self.weekdays = sorted(self.weekdays)
        return self


class ProactivePreferences(StrictModel):
    enabled: bool = Field(default=False, strict=True)
    categories: dict[Category, Annotated[bool, Field(strict=True)]] = Field(
        default_factory=lambda: {c: True for c in CATEGORIES}
    )
    timezone: str | None = None
    quiet_hours: list[QuietWindow] | None = Field(default=None, max_length=14)

    @model_validator(mode="after")
    def valid(self):
        if set(self.categories) != set(CATEGORIES) or any(
            type(v) is not bool for v in self.categories.values()
        ):
            raise ValueError("请明确设置所有建议类别")
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("请填写有效IANA时区") from exc
        if self.quiet_hours and self.timezone is None:
            raise ValueError("安静时段需要明确时区")
        return self


class ProactivePreferenceWrite(StrictModel):
    revision: int = Field(ge=0, strict=True)
    data: ProactivePreferences


class ProactivePreferenceView(StrictModel):
    id: str | None
    kind: Literal["proactive_preferences"] = "proactive_preferences"
    revision: int
    contract_version: Literal["proactive-v1"] = "proactive-v1"
    data: ProactivePreferences


class ProactiveRefresh(StrictModel):
    app_active: bool = Field(strict=True)


class ProactiveAction(StrictModel):
    revision: int = Field(ge=1, strict=True)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: Literal["snooze", "dismiss", "disable_category", "accept"]
    snooze_minutes: int | None = Field(default=None, ge=1, le=10080, strict=True)
    accept_mode: Literal["details", "replan"] | None = None

    @model_validator(mode="after")
    def complete(self):
        if (self.action == "snooze") != (self.snooze_minutes is not None):
            raise ValueError("仅稍后处理需要明确分钟数")
        if (self.action == "accept") != (self.accept_mode is not None):
            raise ValueError("采纳需要明确打开详情或生成待确认草稿")
        return self


class ProactiveSource(StrictModel):
    id: str
    kind: str
    revision: int


class ProactiveSuggestionData(StrictModel):
    schema_version: Literal[1] = 1
    category: Category
    issue_key: str
    fingerprint: str
    title: str
    reasons: list[str]
    gaps: list[str]
    rank: int
    state: Literal[
        "pending", "snoozed", "dismissed", "accepted", "resolved", "superseded"
    ]
    first_seen_at: datetime
    snoozed_until: datetime | None = None
    resolved_at: datetime | None = None
    source_revision: int
    sources: list[ProactiveSource]
    evidence: dict
    task_id: str | None = None
    visible: bool = False


class ProactiveSuggestionView(StrictModel):
    id: str
    kind: Literal["proactive_suggestion"] = "proactive_suggestion"
    revision: int
    data: ProactiveSuggestionData


class ProactiveList(StrictModel):
    contract_version: Literal["proactive-v1"] = "proactive-v1"
    preferences: ProactivePreferenceView
    suggestions: list[ProactiveSuggestionView]
    suppression: Literal["disabled", "inactive", "quiet_hours"] | None = None
    source_revision: int | None = None
    capacity: dict | None = None


class ProactiveActionResult(StrictModel):
    suggestion: ProactiveSuggestionView
    open_task_id: str | None = None
    draft: ResourceView | None = None
    requires_confirmation: bool = False
