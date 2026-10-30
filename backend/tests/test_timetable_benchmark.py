"""Offline benchmark behavior; every source and course in this file is synthetic.

Some tests set synthetic=False only in transient metadata to exercise acceptance
logic. These fixtures do not represent real school material or measured results.
"""

import copy
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts/evaluate-timetable-benchmark.py"


def evaluate(manifest):
    return importlib.import_module("app.timetable_benchmark").evaluate_manifest(
        manifest
    )


def course(slot_id="page1-row1", **changes):
    return {
        "slot_id": slot_id,
        "name": "合成课程Ａ",
        "weekday": 1,
        "weeks": [1, 2],
        "periods": [1, 2],
        **changes,
    }


def sample(number=0, **changes):
    return {
        "sample_id": f"synthetic-test-{number}",
        "layout_id": f"layout-{number % 5}",
        "input_kind": ["image", "text_pdf", "scanned_pdf"][number % 3],
        "source_sha256": hashlib.sha256(
            f"SYNTHETIC-ONLY-{number}".encode()
        ).hexdigest(),
        "anonymized": True,
        "reviewed": True,
        "synthetic": True,
        "prediction_stage": "original",
        "expected": [course()],
        "predicted": [course()],
        **changes,
    }


def manifest(*samples):
    return {"schema_version": 1, "samples": list(samples)}


def test_empty_manifest_reports_unknown_accuracy_and_specific_pending_gaps():
    result = evaluate(manifest())
    assert result["status"] == "not_evaluated"
    assert result["passed"] is False
    assert result["groups"]["real"]["sample_count"] == 0
    assert result["groups"]["real"]["fields"]["name"] == {
        "denominator": 0,
        "correct": 0,
        "incorrect": 0,
        "accuracy": None,
    }
    assert {gap["code"] for gap in result["gaps"]} >= {
        "real_sample_count",
        "layout_count",
        "input_kind_coverage",
        "field_accuracy",
    }


def test_synthetic_perfection_never_satisfies_real_acceptance():
    result = evaluate(manifest(*(sample(i) for i in range(30))))
    assert result["passed"] is False
    assert result["groups"]["real"]["sample_count"] == 0
    assert result["groups"]["synthetic"]["sample_count"] == 30
    assert result["groups"]["synthetic"]["fields"]["weeks"]["accuracy"] == 1.0


def test_acceptance_gate_requires_all_coverage_and_uses_unrounded_accuracy():
    # Transient flags solely exercise the algorithm; no real data are supplied.
    fixtures = [sample(i, synthetic=False) for i in range(30)]
    assert evaluate(manifest(*fixtures))["passed"] is True
    fixtures[0]["predicted"][0]["weekday"] = 2
    result = evaluate(manifest(*fixtures))
    assert result["passed"] is True  # 29/30 exceeds 95%.
    fixtures[1]["predicted"][0]["weekday"] = 2
    result = evaluate(manifest(*fixtures))
    assert result["passed"] is False  # 28/30 is below 95%.
    assert result["groups"]["real"]["fields"]["weekday"]["incorrect"] == 2
    assert any(
        g["code"] == "field_accuracy" and g["field"] == "weekday"
        for g in result["gaps"]
    )


def test_layout_and_each_input_type_are_separate_gate_requirements():
    fixtures = [
        sample(i, synthetic=False, layout_id="one-layout", input_kind="image")
        for i in range(30)
    ]
    result = evaluate(manifest(*fixtures))
    assert result["passed"] is False
    gaps = {g["code"]: g for g in result["gaps"] if g["code"] != "field_accuracy"}
    assert gaps["layout_count"]["actual"] == 1
    assert gaps["input_kind_coverage"]["missing"] == ["scanned_pdf", "text_pdf"]


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"anonymized": False}, "not_anonymized"),
        ({"reviewed": False}, "not_reviewed"),
        ({"prediction_stage": "manually_corrected"}, "not_original_prediction"),
        ({"expected": [], "predicted": []}, "no_expected_courses"),
    ],
)
def test_ineligible_real_metadata_cannot_be_used_to_fill_sample_quota(change, reason):
    fixtures = [sample(i, synthetic=False) for i in range(30)]
    fixtures[0].update(change)
    result = evaluate(manifest(*fixtures))
    assert result["passed"] is False
    assert result["groups"]["real"]["sample_count"] == 29
    assert result["groups"]["excluded_real"]["sample_count"] == 1
    assert reason in result["excluded_samples"][0]["reasons"]


def test_slot_pairing_does_not_guess_from_identical_course_names():
    result = evaluate(
        manifest(sample(expected=[course("p1-r1")], predicted=[course("p1-r2")]))
    )
    group = result["groups"]["synthetic"]
    assert group["courses"] == {"expected": 1, "matched": 0, "missing": 1, "extra": 1}
    assert group["fields"]["name"]["denominator"] == 2
    assert group["fields"]["name"]["incorrect"] == 2
    assert {e["reason"] for e in result["errors"]} >= {"missing_course", "extra_course"}


def test_wrong_missing_extra_fields_are_counted_and_report_never_copies_course_text():
    expected = [course(name="private-course-text", teacher="private-person")]
    predicted = [course(name="wrong-private-text", weekday=None), course("page1-row2")]
    result = evaluate(manifest(sample(expected=expected, predicted=predicted)))
    fields = result["groups"]["synthetic"]["fields"]
    assert fields["name"] == {
        "denominator": 2,
        "correct": 0,
        "incorrect": 2,
        "accuracy": 0.0,
    }
    assert fields["weekday"]["incorrect"] == 2
    assert fields["teacher"]["denominator"] == 1
    reasons = {(e.get("field"), e["reason"]) for e in result["errors"]}
    assert ("name", "incorrect_value") in reasons
    assert ("teacher", "missing_field") in reasons
    assert ("weekday", "missing_field") in reasons
    assert ("name", "extra_prediction") in reasons
    encoded = json.dumps(result)
    assert "private-course-text" not in encoded
    assert "private-person" not in encoded
    assert "wrong-private-text" not in encoded


def test_null_expected_is_unscored_and_does_not_turn_into_zero():
    result = evaluate(
        manifest(
            sample(
                expected=[course(weekday=None, weeks=None, teacher=None)],
                predicted=[course(weekday=7, weeks=[30], teacher="synthetic")],
            )
        )
    )
    fields = result["groups"]["synthetic"]["fields"]
    assert fields["weekday"]["denominator"] == 0
    assert fields["weekday"]["accuracy"] is None
    assert fields["weeks"]["denominator"] == 0
    assert fields["teacher"]["denominator"] == 0
    assert fields["periods"]["correct"] == 1


def test_normalization_is_nfkc_whitespace_and_integer_sorted_sets_only():
    result = evaluate(
        manifest(
            sample(
                expected=[
                    course(name="  合成　课程Ａ \n", weeks=[2, 1, 1], periods=[2, 1])
                ],
                predicted=[course(name="合成 课程A", weeks=[1, 2], periods=[1, 2, 2])],
            )
        )
    )
    assert result["groups"]["synthetic"]["fields"]["name"]["correct"] == 1
    assert result["groups"]["synthetic"]["fields"]["weeks"]["correct"] == 1
    result = evaluate(
        manifest(
            sample(
                expected=[course(name="合成 课程")], predicted=[course(name="合成课程")]
            )
        )
    )
    assert result["groups"]["synthetic"]["fields"]["name"]["incorrect"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "sample_id",
        "source_sha256",
        "source_sha256_case",
        "expected_slot",
        "predicted_slot",
    ],
)
def test_duplicate_sample_and_slot_identity_is_rejected(mutation):
    fixtures = [sample(0), sample(1)]
    if mutation == "sample_id":
        fixtures[1]["sample_id"] = fixtures[0]["sample_id"]
    elif mutation.startswith("source_sha256"):
        fixtures[1]["source_sha256"] = fixtures[0]["source_sha256"]
        if mutation.endswith("case"):
            fixtures[1]["source_sha256"] = fixtures[1]["source_sha256"].upper()
    else:
        key = mutation.split("_")[0]
        fixtures[0][key].append(copy.deepcopy(fixtures[0][key][0]))
    with pytest.raises(ValueError, match="duplicate"):
        evaluate(manifest(*fixtures))


@pytest.mark.parametrize(
    "field,value",
    [
        ("weekday", 0),
        ("weekday", 8),
        ("weekday", True),
        ("weekday", "1"),
        ("weeks", [0]),
        ("weeks", [31]),
        ("weeks", [1.0]),
        ("periods", [False]),
        ("periods", [31]),
        ("name", ""),
    ],
)
def test_out_of_range_and_coerced_field_values_are_rejected(field, value):
    fixture = sample()
    fixture["predicted"][0][field] = value
    with pytest.raises(ValueError):
        evaluate(manifest(fixture))


@pytest.mark.parametrize(
    "change",
    [
        {"date_range": {"starts_on": "2026-02-30", "ends_on": "2026-03-01"}},
        {"date_range": {"starts_on": "2026-03-02", "ends_on": "2026-03-01"}},
        {"date_range": {"starts_on": "2026-3-1", "ends_on": "2026-03-02"}},
        {"input_kind": "pdf"},
        {"source_sha256": "not-a-hash"},
        {"reviewed": "true"},
        {"prediction_stage": "unknown"},
        {"raw_source_text": "must-not-be-saved"},
    ],
)
def test_invalid_dates_metadata_and_unknown_fields_are_rejected(change):
    with pytest.raises(ValueError):
        evaluate(manifest(sample(**change)))


def run_cli(tmp_path, data, *options):
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(data, ensure_ascii=False))
    report = tmp_path / "result.json"
    result = subprocess.run(
        [sys.executable, str(CLI), str(source), "--output", str(report), *options],
        capture_output=True,
        text=True,
    )
    return result, report, source


def test_cli_help_empty_report_and_markdown_exit_two(tmp_path):
    help_result = subprocess.run(
        [sys.executable, str(CLI), "--help"], capture_output=True, text=True
    )
    assert help_result.returncode == 0
    markdown = tmp_path / "summary.md"
    result, report, source = run_cli(tmp_path, manifest(), "--markdown", str(markdown))
    assert result.returncode == 2, result.stderr
    assert json.loads(report.read_text())["status"] == "not_evaluated"
    assert "未达到" in markdown.read_text()
    assert json.loads(source.read_text()) == manifest()


def test_cli_pass_exit_zero_and_invalid_exit_one_without_leaking_values(tmp_path):
    result, report, _ = run_cli(
        tmp_path, manifest(*(sample(i, synthetic=False) for i in range(30)))
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text())["passed"] is True
    report.unlink()
    fixture = sample()
    fixture["expected"][0]["name"] = {"secret": "sensitive-personal-value"}
    result, report, _ = run_cli(tmp_path, manifest(fixture))
    assert result.returncode == 1
    assert not report.exists()
    assert "sensitive-personal-value" not in result.stderr


def test_cli_cannot_overwrite_input_manifest(tmp_path):
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(manifest()))
    result = subprocess.run(
        [sys.executable, str(CLI), str(source), "--output", str(source)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert json.loads(source.read_text()) == manifest()


def test_all_unreadable_ground_truth_does_not_fill_real_sample_quota():
    fixtures = [sample(i, synthetic=False) for i in range(30)]
    unreadable = course(name=None, weekday=None, weeks=None, periods=None)
    fixtures[0].update(expected=[unreadable], predicted=[copy.deepcopy(unreadable)])
    result = evaluate(manifest(*fixtures))
    assert result["passed"] is False
    assert result["groups"]["real"]["sample_count"] == 29
    assert "no_scorable_required_fields" in result["excluded_samples"][0]["reasons"]


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"samples": {}},
    ],
)
def test_manifest_version_and_container_types_are_not_coerced(change):
    data = manifest(sample())
    data.update(change)
    with pytest.raises(ValueError):
        evaluate(data)


def test_missing_provenance_flag_is_rejected_instead_of_assumed_raw():
    fixture = sample()
    del fixture["prediction_stage"]
    with pytest.raises(ValueError):
        evaluate(manifest(fixture))


def test_incomplete_real_coverage_still_marks_material_pending():
    result = evaluate(manifest(sample(synthetic=False)))
    assert result["pending_real_material"] is True
