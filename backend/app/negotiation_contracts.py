"""Explicit, temporary planning intent; no inferred habits or clock times."""

from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from app.contracts import SchedulingConstraint, StrictModel


class IntentInterval(StrictModel):
    starts_at: datetime
    ends_at: datetime


class IntentData(StrictModel):
    description: str = Field(min_length=1, max_length=2000)
    target_date: date
    horizon_days: int = Field(ge=1, le=7, strict=True)
    timezone: str
    protected_intervals: list[IntentInterval] = Field(
        default_factory=list, max_length=30
    )
    preferred_intervals: list[IntentInterval] = Field(
        default_factory=list, max_length=30
    )
    reduced_daily_limit_minutes: int | None = Field(
        default=None, ge=0, le=720, strict=True
    )
    keep_block_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def explicit_intervals(self):
        try:
            zone = ZoneInfo(self.timezone)
        except (ValueError, KeyError) as exc:
            raise ValueError("请提供有效 IANA 时区") from exc
        if not self.description.strip():
            raise ValueError("请描述本轮目标与取舍；不必填写私人原因")
        lower = datetime.combine(self.target_date, time.min, zone)
        upper = lower + timedelta(days=self.horizon_days)
        for interval in self.protected_intervals + self.preferred_intervals:
            SchedulingConstraint(timezone=self.timezone, **interval.model_dump())
            if interval.starts_at < lower or interval.ends_at > upper:
                raise ValueError("临时时段必须位于本轮明确的日期范围内")
        if len(set(self.keep_block_ids)) != len(self.keep_block_ids):
            raise ValueError("保留项不可重复")
        return self


class IntentCreate(StrictModel):
    source_revision: int = Field(ge=1)
    data: IntentData


class IntentAction(StrictModel):
    revision: int = Field(ge=1)
    source_revision: int = Field(ge=1)


class IntentPatch(IntentCreate):
    revision: int = Field(ge=1)


class IntentChoose(IntentAction):
    option_id: Literal["earliest", "preferred"]
