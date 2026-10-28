"""Weekly review: nullable totals, separately attributed estimates and user intent."""

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from app.contracts import StrictModel


class ReviewAction(StrictModel):
    week_start: date
    timezone: str
    revision: int = Field(ge=0, strict=True)
    source_revision: int = Field(ge=0, strict=True)
    action: Literal["accept", "reject", "restore", "reason"]
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid(self):
        validate_week(self.week_start, self.timezone)
        if self.action in ("accept", "reason") and not (self.reason or "").strip():
            raise ValueError("请先写下想调整的内容或原因")
        return self


def validate_week(week_start, timezone):
    if week_start.weekday() != 0:
        raise ValueError("请选择周一作为周起始日期")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("需要有效 IANA 时区") from exc


class PlanTotal(StrictModel):
    status: Literal["complete", "partial", "missing"]
    minutes: float | None
    known_minutes: float
    covered_dates: list[str]
    snapshot_ids: list[str]
    blocks: list[dict]
    gaps: list[str]


class WeeklyReview(StrictModel):
    contract_version: Literal["weekly-review-v1"] = "weekly-review-v1"
    week_start: date
    week_end: date
    timezone: str
    starts_at: str
    ends_at: str
    source_revision: int
    plans: dict[str, PlanTotal]
    execution: dict
    estimates: dict
    gaps: list[str]
    review: dict
    next_week_optimization: Literal["pending_integration"] = "pending_integration"
