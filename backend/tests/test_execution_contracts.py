"""Boundary contracts: completion, estimates and missing observations stay distinct."""

import pytest
from pydantic import ValidationError

from app.execution_contracts import ExecutionSummary, ExecutionWrite


def write(**overrides):
    return ExecutionWrite.model_validate({
        "client_operation_id": "op-one", "execution_id": "session-one",
        "task_id": "task-one", "task_revision": 1,
        "performed_on": "2026-10-28", "timezone": "Asia/Shanghai",
        "actual_minutes": 25, "feedback": "partial", **overrides,
    })


def test_missing_is_not_explicit_zero():
    unknown = ExecutionSummary(task_id="t", source_revision=1)
    zero = ExecutionSummary(task_id="t", source_revision=1, actual_minutes=0)
    assert unknown.actual_minutes is None
    assert zero.actual_minutes == 0


def test_completed_does_not_imply_duration_or_task_completion():
    record = write(actual_minutes=0, feedback="completed")
    assert record.actual_minutes == 0
    assert record.task_status is None
    with pytest.raises(ValidationError):
        write(actual_minutes=None, task_status="completed")


def test_legacy_is_not_precise():
    summary = ExecutionSummary(
        task_id="t", source_revision=3, legacy_estimated_minutes=60,
        planning_spent_minutes=60, unresolved_legacy_minutes=60,
    )
    assert summary.actual_minutes is None
    assert summary.legacy_estimated_minutes == 60


@pytest.mark.parametrize("patch", [
    {"actual_minutes": -1}, {"actual_minutes": 2.5},
    {"timezone": "invented/campus"}, {"step_id": "s"},
    {"plan_block_id": "b", "plan_block_revision": 1},
    {"task_revision": 0}, {"feedback": "guessed"},
    {"actual_minutes": 25, "feedback": "not_started"},
])
def test_invalid_or_incomplete_execution_is_rejected(patch):
    with pytest.raises(ValidationError):
        write(**patch)
