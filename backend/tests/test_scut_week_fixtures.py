import json
from pathlib import Path

import pytest

from app.calendar import parse_week_expression

CASES = json.loads((Path(__file__).parent / "fixtures/scut-timetable/week-cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_scut_week_labels_resolve_or_require_correction(case):
    if "expected" in case:
        assert parse_week_expression(case["text"], case["week_count"]) == case["expected"]
    else:
        with pytest.raises(ValueError):
            parse_week_expression(case["text"], case["week_count"])
