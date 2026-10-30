"""Explicit school rules: no public holiday inference or implicit makeup date."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.contracts import StrictModel

Nonblank = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class SemesterDateMapping(StrictModel):
    original_date: date
    target_date: date

    @model_validator(mode="after")
    def bounded(self):
        if abs((self.target_date - self.original_date).days) > 366:
            raise ValueError("补课与原课日期不能相隔超过一年")
        return self


class SemesterRule(StrictModel):
    operation: Literal["apply"] = "apply"
    rule_kind: Literal["practice_week", "holiday", "makeup", "custom"]
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    reason: Nonblank
    source_scope: Nonblank
    course_ids: list[
        Annotated[str, StringConstraints(min_length=1, max_length=100)]
    ] = Field(min_length=1, max_length=200)
    action: Literal["cancel", "move"]
    start_date: date | None = None
    end_date: date | None = None
    mappings: list[SemesterDateMapping] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def explicit_scope(self):
        if len(set(self.course_ids)) != len(self.course_ids):
            raise ValueError("课程不能重复选择")
        if self.action == "cancel":
            if not self.start_date or not self.end_date or self.mappings:
                raise ValueError("停课需要明确原课日期范围，不能附带补课映射")
            if not 0 <= (self.end_date - self.start_date).days <= 366:
                raise ValueError("原课日期范围应在一年内")
        elif self.start_date or self.end_date or not self.mappings:
            raise ValueError("补课需要逐项明确原课日期与目标日期，不按假期自动推算")
        if len({m.original_date for m in self.mappings}) != len(self.mappings):
            raise ValueError("一个原课日期只能映射到一个目标日期")
        return self


class SemesterUndo(StrictModel):
    operation: Literal["undo"]
    batch_id: str = Field(min_length=1, max_length=100)
    reason: Nonblank


SemesterPayload = Annotated[
    SemesterRule | SemesterUndo, Field(discriminator="operation")
]
