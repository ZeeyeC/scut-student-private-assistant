from datetime import date

import pytest

from app.calendar import expand_calendar
from app.contracts import StudentSettings


def moved(periods):
    settings = StudentSettings(
        week1_monday="2026-10-12",
        periods={
            "1": {"start": "09:00", "end": "09:40"},
            "2": {"start": "09:50", "end": "10:30"},
            "3": {"start": "11:00", "end": "11:40"},
        },
    ).model_dump(mode="json")
    course = {
        "id": "c",
        "data": {"name": "合成课程", "weekday": 3, "weeks": [1], "periods": periods},
    }
    end = "11:40" if periods[-1] == 3 else "10:30"
    exception = {
        "course_id": "c",
        "date": "2026-10-14",
        "starts_at": "2026-10-16T09:00:00+08:00",
        "ends_at": f"2026-10-16T{end}:00+08:00",
        "source": {
            "kind": "semester_calendar",
            "preserve_periods": True,
            "original_date": "2026-10-14",
            "target_date": "2026-10-16",
        },
    }
    return settings, course, exception


def test_calendar_makeup_preserves_nonteaching_gap_and_original_identity():
    settings, course, ex = moved([1, 3])
    events = expand_calendar(
        settings, [course], [ex], date(2026, 10, 14), date(2026, 10, 16)
    )
    assert len(events) == 1
    event = events[0]
    assert event["id"] == "c:2026-10-14"
    assert [p["periods"] for p in event["occupied_intervals"]] == [[1], [3]]
    assert all(
        p["starts_at"].startswith("2026-10-16") for p in event["teaching_intervals"]
    )
    assert event["occupied_intervals"][0]["ends_at"].endswith("09:40:00+08:00")


def test_calendar_makeup_preserves_adjacent_break_and_rejects_clock_changes():
    settings, course, ex = moved([1, 2])
    event = expand_calendar(
        settings, [course], [ex], date(2026, 10, 16), date(2026, 10, 16)
    )[0]
    assert len(event["break_intervals"]) == 1
    assert event["break_intervals"][0]["starts_at"] == "2026-10-16T09:40:00+08:00"
    ex["starts_at"] = "2026-10-16T08:00:00+08:00"
    with pytest.raises(ValueError):
        expand_calendar(
            settings, [course], [ex], date(2026, 10, 16), date(2026, 10, 16)
        )
