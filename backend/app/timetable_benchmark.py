"""Pure offline scoring of explicitly paired, annotated timetable predictions.

No source documents, database, model client, or network are opened here. Reports
identify errors by opaque sample/slot IDs and never echo course field values.
"""

import re
import unicodedata
from datetime import date

REQUIRED_FIELDS = ("name", "weekday", "weeks", "periods")
OPTIONAL_FIELDS = ("teacher", "location", "campus")
FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
INPUT_KINDS = ("image", "text_pdf", "scanned_pdf")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z")
_HASH = re.compile(r"[0-9a-fA-F]{64}\Z")


def _fail(path, message):
    # Paths are constructed from schema keys and list indices, never input text.
    raise ValueError(f"{path}: {message}")


def _object(value, required, optional, path):
    if type(value) is not dict:
        _fail(path, "expected object")
    if not set(required).issubset(value):
        _fail(path, "missing required field")
    if set(value) - set(required) - set(optional):
        _fail(path, "unexpected field")


def _identifier(value, path):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail(path, "expected opaque ASCII identifier (1..100 characters)")
    return value


def _field(value, field, path, expected):
    if value is None:
        return None
    if field in ("name", *OPTIONAL_FIELDS):
        if not isinstance(value, str):
            _fail(path, "expected string or null")
        normalized = " ".join(unicodedata.normalize("NFKC", value).split())
        if not normalized or len(normalized) > 200:
            _fail(path, "expected nonempty string of at most 200 characters")
        return normalized
    if field == "weekday":
        if type(value) is not int or not 1 <= value <= 7:
            _fail(path, "expected integer in 1..7 or null")
        return value
    if type(value) is not list or len(value) > 30 or (expected and not value):
        _fail(path, "expected integer list (1..30 items in ground truth) or null")
    if any(type(number) is not int or not 1 <= number <= 30 for number in value):
        _fail(path, "list values must be integers in 1..30")
    return sorted(set(value))


def _courses(value, path, expected):
    if type(value) is not list:
        _fail(path, "expected course list")
    result = {}
    required = ("slot_id", *REQUIRED_FIELDS) if expected else ("slot_id",)
    for index, row in enumerate(value):
        row_path = f"{path}[{index}]"
        _object(row, required, set(FIELDS) - set(required), row_path)
        slot = _identifier(row["slot_id"], f"{row_path}.slot_id")
        if slot in result:
            _fail(row_path, "duplicate slot_id")
        result[slot] = {
            field: _field(row[field], field, f"{row_path}.{field}", expected)
            for field in FIELDS
            if field in row
        }
    return result


def _validate(manifest):
    _object(manifest, ("schema_version", "samples"), (), "manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        _fail("manifest.schema_version", "only integer schema version 1 is supported")
    if type(manifest["samples"]) is not list:
        _fail("manifest.samples", "expected sample list")
    samples, seen_ids, seen_hashes = [], set(), set()
    required = (
        "sample_id",
        "layout_id",
        "input_kind",
        "source_sha256",
        "anonymized",
        "reviewed",
        "synthetic",
        "prediction_stage",
        "expected",
        "predicted",
    )
    for index, raw in enumerate(manifest["samples"]):
        path = f"manifest.samples[{index}]"
        _object(raw, required, ("date_range",), path)
        row = dict(raw)
        for field in ("sample_id", "layout_id"):
            row[field] = _identifier(raw[field], f"{path}.{field}")
        if row["sample_id"] in seen_ids:
            _fail(path, "duplicate sample_id")
        seen_ids.add(row["sample_id"])
        digest = raw["source_sha256"]
        if not isinstance(digest, str) or not _HASH.fullmatch(digest):
            _fail(f"{path}.source_sha256", "expected 64 hexadecimal characters")
        row["source_sha256"] = digest.lower()
        if row["source_sha256"] in seen_hashes:
            _fail(path, "duplicate source_sha256")
        seen_hashes.add(row["source_sha256"])
        if raw["input_kind"] not in INPUT_KINDS:
            _fail(f"{path}.input_kind", "expected image, text_pdf, or scanned_pdf")
        for field in ("anonymized", "reviewed", "synthetic"):
            if type(raw[field]) is not bool:
                _fail(f"{path}.{field}", "expected boolean")
        if raw["prediction_stage"] not in ("original", "manually_corrected"):
            _fail(f"{path}.prediction_stage", "expected original or manually_corrected")
        if "date_range" in raw:
            dates = raw["date_range"]
            _object(dates, ("starts_on", "ends_on"), (), f"{path}.date_range")
            parsed = []
            for key in ("starts_on", "ends_on"):
                value = dates[key]
                if not isinstance(value, str) or not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", value
                ):
                    _fail(f"{path}.date_range.{key}", "expected ISO YYYY-MM-DD date")
                try:
                    parsed.append(date.fromisoformat(value))
                except ValueError:
                    _fail(f"{path}.date_range.{key}", "invalid calendar date")
            if parsed[1] < parsed[0]:
                _fail(f"{path}.date_range", "end date precedes start date")
        for field in ("expected", "predicted"):
            row[field] = _courses(raw[field], f"{path}.{field}", field == "expected")
        samples.append(row)
    return samples


def _group():
    return {
        "sample_count": 0,
        "layout_ids": [],
        "input_kind_counts": dict.fromkeys(INPUT_KINDS, 0),
        "courses": dict.fromkeys(("expected", "matched", "missing", "extra"), 0),
        "fields": {
            field: {"denominator": 0, "correct": 0, "incorrect": 0, "accuracy": None}
            for field in FIELDS
        },
    }


def _score(sample, group_name, group, errors):
    group["sample_count"] += 1
    if sample["layout_id"] not in group["layout_ids"]:
        group["layout_ids"].append(sample["layout_id"])
    group["input_kind_counts"][sample["input_kind"]] += 1
    expected, predicted = sample["expected"], sample["predicted"]
    group["courses"]["expected"] += len(expected)

    def error(slot, reason, field=None):
        entry = {
            "group": group_name,
            "sample_id": sample["sample_id"],
            "slot_id": slot,
            "reason": reason,
        }
        if field is not None:
            entry["field"] = field
        errors.append(entry)

    for slot, truth in expected.items():
        found = predicted.get(slot)
        group["courses"]["matched" if found is not None else "missing"] += 1
        if found is None:
            error(slot, "missing_course")
        for field, value in truth.items():
            if value is None:
                continue  # Illegible/unlabelled ground truth has no denominator.
            metric = group["fields"][field]
            metric["denominator"] += 1
            actual = found.get(field) if found is not None else None
            if actual == value:
                metric["correct"] += 1
            else:
                metric["incorrect"] += 1
                error(
                    slot,
                    "missing_field" if actual is None else "incorrect_value",
                    field,
                )
    for slot, found in predicted.items():
        if slot in expected:
            continue
        group["courses"]["extra"] += 1
        error(slot, "extra_course")
        # Every extra course penalizes all four required fields, even if that
        # prediction omitted a field. Optional fields penalize supplied values.
        for field in FIELDS:
            if field in REQUIRED_FIELDS or found.get(field) is not None:
                group["fields"][field]["denominator"] += 1
                group["fields"][field]["incorrect"] += 1
                error(slot, "extra_prediction", field)


def evaluate_manifest(manifest):
    """Validate then score v1 metadata, without mutating it or exposing values.

    Only reviewed, anonymized, non-synthetic original predictions enter the real
    acceptance gate. Declared provenance still requires human audit; this tool
    cannot prove that supplied source hashes or flags describe real material.
    """
    samples = _validate(manifest)
    groups = {name: _group() for name in ("real", "synthetic", "excluded_real")}
    errors, excluded = [], []
    for sample in samples:
        reasons = []
        if not sample["anonymized"]:
            reasons.append("not_anonymized")
        if not sample["reviewed"]:
            reasons.append("not_reviewed")
        if sample["prediction_stage"] != "original":
            reasons.append("not_original_prediction")
        if not sample["expected"]:
            reasons.append("no_expected_courses")
        elif not any(
            course.get(field) is not None
            for course in sample["expected"].values()
            for field in REQUIRED_FIELDS
        ):
            reasons.append("no_scorable_required_fields")
        if sample["synthetic"]:
            name = "synthetic"
        elif reasons:
            name = "excluded_real"
            excluded.append({"sample_id": sample["sample_id"], "reasons": reasons})
        else:
            name = "real"
        _score(sample, name, groups[name], errors)
    for group in groups.values():
        group["layout_ids"].sort()
        group["layout_count"] = len(group["layout_ids"])
        for metric in group["fields"].values():
            if metric["denominator"]:
                metric["accuracy"] = metric["correct"] / metric["denominator"]
    real, gaps = groups["real"], []
    if real["sample_count"] < 30:
        gaps.append(
            {"code": "real_sample_count", "actual": real["sample_count"], "minimum": 30}
        )
    if real["layout_count"] < 5:
        gaps.append(
            {"code": "layout_count", "actual": real["layout_count"], "minimum": 5}
        )
    missing = sorted(
        kind for kind, count in real["input_kind_counts"].items() if not count
    )
    if missing:
        gaps.append({"code": "input_kind_coverage", "missing": missing})
    for field in REQUIRED_FIELDS:
        metric = real["fields"][field]
        if (
            not metric["denominator"]
            or metric["correct"] * 100 < metric["denominator"] * 95
        ):
            gaps.append(
                {"code": "field_accuracy", "field": field, "minimum": 0.95, **metric}
            )
    return {
        "schema_version": 1,
        "status": "evaluated" if real["sample_count"] else "not_evaluated",
        "passed": not gaps,
        "assessment_scope": "reviewed_anonymized_real_original_predictions_only",
        "pending_real_material": any(
            gap["code"] in ("real_sample_count", "layout_count", "input_kind_coverage")
            for gap in gaps
        ),
        "normalization": {
            "strings": "NFKC; trim and collapse Unicode whitespace; retain internal word boundaries; case-sensitive",
            "weekday": "strict integer 1..7; no string/boolean coercion",
            "weeks_periods": "strict integers 1..30; sorted unique set; null is unknown",
            "pairing": "human-verified slot_id only; no name or position guessing",
            "extra_predictions": "add one error/denominator to each required field; supplied optional fields likewise",
            "accuracy": "correct / denominator (0..1); null when denominator=0; gate uses unrounded ratio",
        },
        "groups": groups,
        "excluded_samples": excluded,
        "errors": errors,
        "gaps": gaps,
    }


def render_markdown(report):
    """Render aggregate numbers only; no field text from sources/predictions."""
    lines = [
        "# 课表识别离线评测",
        "",
        "验收通过。" if report["passed"] else "未达到真实样本验收门槛。",
        "",
    ]
    if report["status"] == "not_evaluated":
        lines.extend(["真实材料待提供；未执行真实准确率验收，空分母准确率为未知。", ""])
    for name, group in report["groups"].items():
        lines.extend(
            [
                f"## {name}",
                "",
                f"样本 {group['sample_count']}；布局 {group['layout_count']}；漏识 {group['courses']['missing']}；多识 {group['courses']['extra']}。",
                "",
                "| 字段 | 分母 | 正确 | 错误 | 准确率 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for field, metric in group["fields"].items():
            accuracy = (
                "未知" if metric["accuracy"] is None else f"{metric['accuracy']:.2%}"
            )
            lines.append(
                f"| {field} | {metric['denominator']} | {metric['correct']} | {metric['incorrect']} | {accuracy} |"
            )
        lines.append("")
    lines.extend(["## 具体缺口", ""])
    for gap in report["gaps"]:
        lines.append(
            f"- {gap['code']}"
            + (f" / {gap['field']}" if "field" in gap else "")
            + (f" / {', '.join(gap['missing'])}" if "missing" in gap else "")
        )
    lines.extend(
        [
            "",
            "详细分母、覆盖、逐项错误及排除原因见配套JSON；合成结果不计入真实门槛。",
            "",
        ]
    )
    return "\n".join(lines)
