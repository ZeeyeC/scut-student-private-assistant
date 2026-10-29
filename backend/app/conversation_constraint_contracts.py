"""A conversation candidate may be incomplete; no implicit afternoon hours."""

from datetime import date, time
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from app.contracts import StrictModel


class ConstraintIntentFields(StrictModel):
    day_expression: str | None = Field(default=None, max_length=100)
    start_time: str | None = None
    end_time: str | None = None
    end_day_offset: int = Field(default=0, ge=0, le=1, strict=True)
    recurrence: Literal["once", "weekly"] = "once"
    weekdays: list[Annotated[int, Field(ge=1, le=7, strict=True)]] = Field(
        default_factory=list, max_length=7
    )
    valid_until: date | None = None
    strength: Literal["hard", "soft"] = "hard"
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError) as exc:
                raise ValueError("请输入有效IANA时区") from exc
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def minute_clock(cls, value):
        if value is None:
            return None
        parsed = time.fromisoformat(value)
        if parsed.tzinfo or parsed.second or parsed.microsecond:
            raise ValueError("请使用明确的当地整分钟时刻，不带时区")
        return parsed.strftime("%H:%M")


class ConstraintIntentCreate(StrictModel):
    data: ConstraintIntentFields
    thread_id: str | None = None


class ConstraintIntentPatch(StrictModel):
    revision: int = Field(ge=1, strict=True)
    changes: dict[str, Any]


class ConstraintIntentAction(StrictModel):
    revision: int = Field(ge=1, strict=True)
