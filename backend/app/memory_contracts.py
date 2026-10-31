"""Confirmed local memory; suggestions never silently become facts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import StrictModel
from app.db import now
from app.profile_contracts import ProfilePreferences

ProfileField = Literal["focus_minutes", "break_minutes", "daily_load_minutes"]


class MemoryProposal(StrictModel):
    key: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=400)
    category: Literal["study_preference", "interaction_preference"]
    expires_at: datetime | None = None
    profile_field: ProfileField | None = None
    profile_value: int | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def valid(self):
        if not self.key.strip() or not self.content.strip():
            raise ValueError("记忆名称和内容不能为空")
        if self.expires_at and (
            self.expires_at.tzinfo is None or self.expires_at <= now()
        ):
            raise ValueError("有效期需要带时区的未来时间")
        if (self.profile_field is None) != (self.profile_value is None):
            raise ValueError("结构化偏好需要同时提供字段和值")
        if self.profile_field:
            if (
                self.category != "study_preference"
                or self.key != self.profile_field
                or self.expires_at
            ):
                raise ValueError("永久学习偏好需要使用标准字段且不设有效期")
            ProfilePreferences(**{self.profile_field: self.profile_value})
        return self


class MemoryPreferencesWrite(StrictModel):
    revision: int = Field(ge=0, strict=True)
    recall_enabled: bool
    suggestions_enabled: bool


class MemoryAction(StrictModel):
    revision: int = Field(ge=1, strict=True)


class MemoryReset(StrictModel):
    revision: int = Field(ge=0, strict=True)
    confirm: Literal[True]
