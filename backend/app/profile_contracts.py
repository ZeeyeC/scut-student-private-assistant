"""Explicit, nullable preferences. These are soft preferences, never hard constraints."""

from datetime import date, datetime, time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from app.contracts import StrictModel

Weekday = Annotated[int, Field(ge=1, le=7, strict=True)]


class ProfileWindow(StrictModel):
    weekdays: list[Weekday] = Field(min_length=1, max_length=7)
    start: time
    end: time

    @model_validator(mode="after")
    def valid_window(self):
        if any(t.tzinfo or t.second or t.microsecond for t in (self.start, self.end)):
            raise ValueError("时段请使用当地整分钟时间，不带时区")
        if self.start >= self.end:
            raise ValueError("结束时间必须晚于开始时间；跨午夜请拆成多个时段")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("时段内星期不能重复")
        return self


class StudyWindow(ProfileWindow):
    task_type: Literal["any", "deep", "review"] = "any"


class EnergyWindow(ProfileWindow):
    level: Literal["low", "medium", "high"]


class ProfilePreferences(StrictModel):
    preferred_study_windows: list[StudyWindow] | None = Field(
        default=None, max_length=28
    )
    energy_windows: list[EnergyWindow] | None = Field(default=None, max_length=28)
    focus_minutes: int | None = Field(default=None, ge=5, le=240, strict=True)
    break_minutes: int | None = Field(default=None, ge=0, le=120, strict=True)
    review_interval_days: int | None = Field(default=None, ge=1, le=365, strict=True)
    daily_load_minutes: int | None = Field(default=None, ge=0, le=720, strict=True)
    leisure_protection: Literal["prefer_protect", "flexible"] | None = None

    @model_validator(mode="after")
    def non_overlapping(self):
        for windows in (self.preferred_study_windows, self.energy_windows):
            for i, a in enumerate(windows or []):
                if any(
                    set(a.weekdays) & set(b.weekdays)
                    and a.start < b.end
                    and b.start < a.end
                    for b in windows[i + 1 :]
                ):
                    raise ValueError("同类偏好时段在同一天不能重叠")
        return self


class ProfileInput(StrictModel):
    timezone: str
    effective_from: date | None = None
    effective_until: date | None = None
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)

    @model_validator(mode="after")
    def valid_range(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("需要有效 IANA 时区") from exc
        if (
            self.effective_from
            and self.effective_until
            and self.effective_until < self.effective_from
        ):
            raise ValueError("有效截止日期不能早于起始日期")
        return self


class ProfileWrite(StrictModel):
    revision: int = Field(ge=0, strict=True)
    data: ProfileInput


class ProfileReset(StrictModel):
    revision: int = Field(ge=0, strict=True)


class ProfileData(StrictModel):
    schema_version: Literal[1] = 1
    timezone: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)
    source: Literal["unknown", "user"] = "unknown"
    confirmed: bool = False
    sample_count: Literal[0] = 0
    updated_at: datetime | None = None


class ProfileView(StrictModel):
    id: str | None
    kind: Literal["user_profile"] = "user_profile"
    revision: int
    source_revision: int
    contract_version: Literal["profile-v1"] = "profile-v1"
    data: ProfileData
    # No inferred suggestions are generated in this increment.
    suggestions: list[dict] = Field(default_factory=list)
