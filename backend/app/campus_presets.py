"""Trusted user-supplied SCUT three-campus period templates."""

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict

CampusPresetId = Literal["wushan", "guoji", "daxuecheng"]

_ALIASES: dict[str, CampusPresetId] = {
    "wushan": "wushan",
    "五山": "wushan",
    "五山校区": "wushan",
    "guoji": "guoji",
    "international": "guoji",
    "国际": "guoji",
    "国际校区": "guoji",
    "daxuecheng": "daxuecheng",
    "university_town": "daxuecheng",
    "大学城": "daxuecheng",
    "大学城校区": "daxuecheng",
}

WUSHAN_PERIODS: dict[str, dict[str, str]] = {
    "1": {"start": "08:00", "end": "08:45"},
    "2": {"start": "08:55", "end": "09:40"},
    "3": {"start": "10:00", "end": "10:45"},
    "4": {"start": "10:55", "end": "11:40"},
    "5": {"start": "14:30", "end": "15:15"},
    "6": {"start": "15:25", "end": "16:10"},
    "7": {"start": "16:20", "end": "17:05"},
    "8": {"start": "17:15", "end": "18:00"},
    "9": {"start": "19:00", "end": "19:45"},
    "10": {"start": "19:55", "end": "20:40"},
    "11": {"start": "20:50", "end": "21:35"},
    "12": {"start": "21:35", "end": "22:00"},
}

GUOJI_DAXUECHENG_PERIODS: dict[str, dict[str, str]] = {
    "1": {"start": "08:50", "end": "09:35"},
    "2": {"start": "09:40", "end": "10:25"},
    "3": {"start": "10:40", "end": "11:25"},
    "4": {"start": "11:30", "end": "12:15"},
    "5": {"start": "14:00", "end": "14:45"},
    "6": {"start": "14:50", "end": "15:35"},
    "7": {"start": "15:45", "end": "16:30"},
    "8": {"start": "16:35", "end": "17:20"},
    "9": {"start": "19:00", "end": "19:45"},
    "10": {"start": "19:55", "end": "20:40"},
    "11": {"start": "20:50", "end": "21:35"},
    "12": {"start": "21:35", "end": "22:00"},
}


class CampusPresetWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str
    end: str


class CampusPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: CampusPresetId
    label: str
    periods: dict[str, CampusPresetWindow]
    classroom_open: str
    morning_exercise: str
    note: str


CAMPUS_PRESETS: list[dict] = [
    {
        "id": "wushan",
        "label": "五山",
        "periods": deepcopy(WUSHAN_PERIODS),
        "classroom_open": "07:00",
        "morning_exercise": "09:40-10:00",
        "note": "课室开放 07:00；课间操 09:40-10:00（仅作说明，不作为第 13/14 节，不生成固定课程事件）",
    },
    {
        "id": "guoji",
        "label": "国际",
        "periods": deepcopy(GUOJI_DAXUECHENG_PERIODS),
        "classroom_open": "07:00",
        "morning_exercise": "10:25-10:40",
        "note": "课室开放 07:00；课间操 10:25-10:40（仅作说明，不作为第 13/14 节，不生成固定课程事件）",
    },
    {
        "id": "daxuecheng",
        "label": "大学城",
        "periods": deepcopy(GUOJI_DAXUECHENG_PERIODS),
        "classroom_open": "07:00",
        "morning_exercise": "10:25-10:40",
        "note": "课室开放 07:00；课间操 10:25-10:40（仅作说明，不作为第 13/14 节，不生成固定课程事件）",
    },
]

PRESET_BY_ID: dict[str, dict] = {item["id"]: item for item in CAMPUS_PRESETS}


def normalize_campus_preset(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return _ALIASES.get(value.strip(), value)
    return value


def preset_periods(preset_id: str) -> dict[str, dict[str, str]]:
    normalized = normalize_campus_preset(preset_id)
    if normalized not in PRESET_BY_ID:
        raise ValueError("未知校区节次模板")
    return {
        k: {"start": v["start"] + ":00", "end": v["end"] + ":00"}
        if len(v["start"]) == 5
        else deepcopy(v)
        for k, v in PRESET_BY_ID[normalized]["periods"].items()
    }


def canonical_periods(periods: dict | None) -> dict[str, dict[str, str]]:
    if not periods:
        return {}
    return {
        str(k): {
            "start": str(v["start"])[:5],
            "end": str(v["end"])[:5],
        }
        for k, v in periods.items()
        if isinstance(v, dict) and "start" in v and "end" in v
    }


def effective_settings(settings_data: dict, payload: dict | None = None) -> dict:
    preset = normalize_campus_preset((payload or {}).get("campus_preset"))
    if preset in PRESET_BY_ID:
        return {
            **deepcopy(settings_data),
            "campus_preset": preset,
            "periods": preset_periods(preset),
        }
    saved_preset = normalize_campus_preset(settings_data.get("campus_preset"))
    if saved_preset in PRESET_BY_ID and not settings_data.get("periods"):
        return {
            **deepcopy(settings_data),
            "campus_preset": saved_preset,
            "periods": preset_periods(saved_preset),
        }
    return deepcopy(settings_data)


def reconcile_settings_preset(old_data: dict | None, new_data: dict) -> dict:
    preset = normalize_campus_preset(new_data.get("campus_preset"))
    if not preset:
        return {**new_data, "campus_preset": None}
    template = preset_periods(preset)
    canon_template = canonical_periods(template)
    curr_periods = canonical_periods(new_data.get("periods"))
    old_preset = normalize_campus_preset((old_data or {}).get("campus_preset"))
    old_periods = canonical_periods((old_data or {}).get("periods"))
    if curr_periods == canon_template:
        return {**new_data, "campus_preset": preset, "periods": template}
    if not curr_periods or (preset != old_preset and curr_periods == old_periods):
        return {**new_data, "campus_preset": preset, "periods": template}
    return {**new_data, "campus_preset": None}
