"""Read-only capacity facts, computed from the planner's exact free windows."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.contracts import StrictModel


class CapacityWindow(StrictModel):
    starts_at: datetime
    ends_at: datetime
    minutes: int = Field(ge=0)


class CapacityDay(StrictModel):
    date: date
    free_windows: list[CapacityWindow]
    free_minutes: int = Field(ge=0)
    budget_remaining_minutes: int = Field(ge=0)
    capacity_upper_bound_minutes: int = Field(ge=0)
    proposed_minutes: int = Field(ge=0)


class UnallocatedWork(StrictModel):
    task_id: str | None = None
    step_id: str | None = None
    title: str
    remaining_minutes: int | None
    reason: str


class CapacityChanges(StrictModel):
    added: int = Field(ge=0)
    retained: int = Field(ge=0)
    removed: int = Field(ge=0)


class CapacityReport(StrictModel):
    schema_version: Literal[1] = 1
    scope: Literal["today", "range"]
    target_date: date
    horizon_days: int
    timezone: str
    calculated_at: datetime
    source_revision: int
    rule_version: str
    days: list[CapacityDay]
    capacity_upper_bound_minutes: int = Field(ge=0)
    required_minutes: int = Field(ge=0)
    reserved_work_minutes: int = Field(ge=0)
    proposed_minutes: int = Field(ge=0)
    unallocated_minutes: int = Field(ge=0)
    unknown_estimate_count: int = Field(ge=0)
    unscheduled: list[UnallocatedWork]
    warnings: list[str]
    changes: CapacityChanges


def capacity_report(p, result, free, used, required, reserved, preserved, tz):
    """Keep time upper bounds separate from actually schedulable work.

    `free` is captured before allocation; deadlines, dependencies and fragmented
    time can make proposed work smaller. Plan minutes are never actual effort.
    """
    preserved_ids = {b["id"] for b in preserved}
    proposed = {day: 0 for day in free}
    for block in result["blocks"]:
        if block["id"] in preserved_ids:
            continue
        a = datetime.fromisoformat(block["starts_at"])
        b = datetime.fromisoformat(block["ends_at"])
        day = a.astimezone(tz).date()
        if day in proposed:
            proposed[day] += int((b - a).total_seconds() // 60)
    days = []
    for day, windows in free.items():
        windows = [
            {
                "starts_at": a.isoformat(),
                "ends_at": b.isoformat(),
                "minutes": int((b - a).total_seconds() // 60),
            }
            for a, b in windows
        ]
        free_minutes = sum(w["minutes"] for w in windows)
        budget = max(0, int(p["settings"]["daily_limit_minutes"] - used[day]))
        days.append(
            {
                "date": day.isoformat(),
                "free_windows": windows,
                "free_minutes": free_minutes,
                "budget_remaining_minutes": budget,
                "capacity_upper_bound_minutes": min(free_minutes, budget),
                "proposed_minutes": proposed[day],
            }
        )
    return CapacityReport.model_validate(
        {
            "scope": p.get("scope", "range"),
            "target_date": p["target_date"],
            "horizon_days": p["horizon_days"],
            "timezone": p["settings"]["timezone"],
            "calculated_at": p["now_utc"],
            "source_revision": p["source_revision"],
            "rule_version": result["rule_version"],
            "days": days,
            "capacity_upper_bound_minutes": sum(
                d["capacity_upper_bound_minutes"] for d in days
            ),
            "required_minutes": required,
            "reserved_work_minutes": int(reserved),
            "proposed_minutes": sum(proposed.values()),
            "unallocated_minutes": sum(
                u["remaining_minutes"] or 0 for u in result["unscheduled"]
            ),
            "unknown_estimate_count": sum(
                u["remaining_minutes"] is None for u in result["unscheduled"]
            ),
            "unscheduled": result["unscheduled"],
            "warnings": result["warnings"],
            "changes": {
                key: len(result["changes"][key + "_ids"])
                for key in ("added", "retained", "removed")
            },
        }
    ).model_dump(mode="json")
