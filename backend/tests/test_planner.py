from datetime import datetime

from app.planner import build_plan


def fixture():
    return {
        "now_utc": datetime.fromisoformat("2026-10-14T02:30:00+00:00"),
        "target_date": "2026-10-14",
        "horizon_days": 1,
        "settings": {
            "timezone": "Asia/Shanghai",
            "study_windows": [{"start": "09:00", "end": "18:00"}],
            "buffer_minutes": 10,
            "daily_limit_minutes": 180,
            "max_block_minutes": 60,
            "min_block_minutes": 15,
        },
        "occurrences": [
            {
                "starts_at": "2026-10-14T10:00:00+08:00",
                "ends_at": "2026-10-14T11:00:00+08:00",
            }
        ],
        "fixed_events": [],
        "tasks": [
            {
                "id": "t1",
                "data": {
                    "due_at": "2026-10-14T18:00:00+08:00",
                    "status": "open",
                    "priority": 2,
                },
            }
        ],
        "steps": [
            {
                "id": "a",
                "data": {
                    "task_id": "t1",
                    "estimated_minutes": 120,
                    "spent_minutes": 0,
                    "dependency_ids": [],
                    "status": "open",
                },
            },
            {
                "id": "b",
                "data": {
                    "task_id": "t1",
                    "estimated_minutes": 60,
                    "spent_minutes": 0,
                    "dependency_ids": ["a"],
                    "status": "open",
                },
            },
        ],
        "preserved_blocks": [],
        "source_revision": 1,
    }


def test_buffers_past_daily_limit_long_dependency_and_stable():
    p = fixture()
    r = build_plan(p)
    assert len(r["blocks"]) == 3
    assert r == build_plan(p)
    a = [b for b in r["blocks"] if b["step_id"] == "a"]
    b = [b for b in r["blocks"] if b["step_id"] == "b"]
    assert len(a) == 2
    assert b[0]["starts_at"] >= a[-1]["ends_at"]
    for block in r["blocks"]:
        start = datetime.fromisoformat(block["starts_at"])
        end = datetime.fromisoformat(block["ends_at"])
        assert start >= datetime.fromisoformat("2026-10-14T11:10:00+08:00")
        assert (end - start).total_seconds() <= 3600
    assert (
        sum(
            (
                datetime.fromisoformat(b["ends_at"])
                - datetime.fromisoformat(b["starts_at"])
            ).total_seconds()
            / 60
            for b in r["blocks"]
        )
        == 180
    )


def test_deadline_capacity_overdue_unknown_and_locks():
    p = fixture()
    p["tasks"][0]["data"]["due_at"] = "2026-10-14T12:00:00+08:00"
    r = build_plan(p)
    assert sum(x["remaining_minutes"] for x in r["unscheduled"]) == 130
    assert all(
        datetime.fromisoformat(b["ends_at"])
        <= datetime.fromisoformat("2026-10-14T12:00:00+08:00")
        for b in r["blocks"]
    )
    p["tasks"][0]["data"]["due_at"] = "2026-10-13T12:00:00+08:00"
    r = build_plan(p)
    assert not r["blocks"]
    assert any("补救" in x["reason"] for x in r["unscheduled"])
    p["tasks"][0]["data"]["due_at"] = None
    p["preserved_blocks"] = [
        {
            "id": "lock",
            "task_id": "t1",
            "step_id": "a",
            "starts_at": "2026-10-14T11:30:00+08:00",
            "ends_at": "2026-10-14T12:30:00+08:00",
            "locked": True,
            "status": "suggested",
        }
    ]
    r = build_plan(p)
    assert r["blocks"][0]["id"] == "lock"
    assert (
        sum(
            (
                datetime.fromisoformat(b["ends_at"])
                - datetime.fromisoformat(b["starts_at"])
            ).total_seconds()
            / 60
            for b in r["blocks"]
        )
        <= 180
    )
    assert all(
        datetime.fromisoformat(b["starts_at"])
        >= datetime.fromisoformat("2026-10-14T12:30:00+08:00")
        for b in r["blocks"]
        if b["step_id"] == "b"
    )


def test_dst_aware_and_no_inverted_time():
    p = fixture()
    p.update(
        now_utc=datetime.fromisoformat("2026-03-08T05:00:00+00:00"),
        target_date="2026-03-08",
        occurrences=[],
    )
    p["settings"]["timezone"] = "America/New_York"
    p["settings"]["study_windows"] = [{"start": "01:00", "end": "04:00"}]
    p["tasks"][0]["data"]["due_at"] = None
    r = build_plan(p)
    assert r["blocks"]
    for b in r["blocks"]:
        assert datetime.fromisoformat(b["ends_at"]) > datetime.fromisoformat(
            b["starts_at"]
        )


def test_invalid_locked_block_is_preserved_but_not_counted_before_deadline():
    p = fixture()
    p["steps"] = p["steps"][:1]
    p["preserved_blocks"] = [
        {
            "id": "locked-late",
            "task_id": "t1",
            "step_id": "a",
            "starts_at": "2026-10-15T14:00:00+08:00",
            "ends_at": "2026-10-15T15:00:00+08:00",
            "locked": True,
            "status": "suggested",
        }
    ]
    r = build_plan(p)
    assert r["blocks"][0]["id"] == "locked-late"
    assert r["unscheduled"][0]["remaining_minutes"] == 120
    assert "解锁" in r["unscheduled"][0]["reason"]
    assert r["warnings"]
    assert not r["removed_blocks"]


def test_task_without_steps_is_not_silently_omitted():
    p = fixture()
    p["tasks"][0]["data"]["title"] = "阅读文献"
    p["steps"] = []
    result = build_plan(p)
    assert result["blocks"] == []
    assert result["unscheduled"] == [
        {
            "task_id": "t1",
            "title": "阅读文献",
            "remaining_minutes": None,
            "reason": "尚无可排程步骤，请填写预计耗时或确认任务拆解",
        }
    ]


def test_plan_includes_existing_calendar_agenda_without_inventing_study_work():
    p = fixture()
    p["tasks"] = []
    p["steps"] = []
    p["fixed_events"] = [
        {
            "title": "彩排",
            "starts_at": "2026-10-14T17:30:00+08:00",
            "ends_at": "2026-10-14T19:00:00+08:00",
        }
    ]
    result = build_plan(p)
    assert result["blocks"] == []
    assert any(e["title"] == "彩排" for e in result["fixed_agenda"])
