"""Deterministic date boundaries; never invent end-of-day deadlines."""

import re
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException


def resolve_academic_deadline(settings, expression):
    text = re.sub(r"\s+", "", expression or "").strip("，。！! ")
    match = re.fullmatch(r"第?(\d{1,2})周(之前|以前|前|结束前)", text)
    if not match:
        return {
            "resolved": False,
            "reason": "描述没有唯一的教学周边界，请补充具体日期和钟点",
        }
    week = int(match[1])
    if not settings.get("week1_monday"):
        return {"resolved": False, "reason": "请先在设置中确认学期第1周周一日期"}
    if not 1 <= week <= settings["week_count"]:
        return {"resolved": False, "reason": "周次超过当前学期范围"}
    before = match[2] in {"之前", "以前", "前"}
    day = date.fromisoformat(settings["week1_monday"]) + timedelta(
        weeks=week - int(before)
    )
    instant = datetime.combine(day, time.min, ZoneInfo(settings["timezone"]))
    label = f"第{week}周{'开始' if before else '结束'}前（{day.isoformat()} 00:00，{settings['timezone']}）"
    return {
        "resolved": True,
        "due_at": instant.isoformat(),
        "explanation": f"按首周周一 {settings['week1_monday']} 推算：{label}；这是周次边界，可在保存前修改",
        "basis": {
            "expression": expression,
            "week1_monday": settings["week1_monday"],
            "timezone": settings["timezone"],
        },
    }


def reference_day(value, zone):
    if not value:
        return None
    if isinstance(value, str):
        if len(value) == 10:
            return date.fromisoformat(value)
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        # SQLite returns naive UTC even for timezone=True columns.
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc)
            .astimezone(ZoneInfo(zone))
            .date()
        )
    return value


def resolve_calendar_deadline(settings, expression, reference_time=None):
    text = re.sub(r"\s+", "", expression or "").strip("，。！! ")
    boundary = re.fullmatch(r"(.+?)(之前|以前|前|结束前)", text)
    unresolved = {
        "resolved": False,
        "reason": "没有唯一日期边界或缺少消息年份，请用自然语言补充",
    }
    if not boundary:
        return unresolved
    raw, relation = boundary.groups()
    anchor = reference_day(reference_time, settings["timezone"])
    inferred = False
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            day = date.fromisoformat(raw)
        elif raw in {"今天", "明天", "后天"}:
            if not anchor:
                return unresolved
            day = anchor + timedelta(days={"今天": 0, "明天": 1, "后天": 2}[raw])
            inferred = True
        else:
            match = re.fullmatch(
                r"(?:(\d{4})年|(今年|明年))?(\d{1,2})月(\d{1,2})[日号]", raw
            )
            if not match:
                return unresolved
            year, relative_year, month, dom = match.groups()
            if not year and not anchor:
                return unresolved
            inferred = not bool(year)
            year = int(year) if year else anchor.year + int(relative_year == "明年")
            day = date(year, int(month), int(dom))
        if relation == "结束前":
            day += timedelta(days=1)
    except ValueError:
        return {"resolved": False, "reason": "日期无效，请核对月份、日期和年份"}
    instant = datetime.combine(day, time.min, ZoneInfo(settings["timezone"]))
    return {
        "resolved": True,
        "due_at": instant.isoformat(),
        "explanation": (
            f"按消息日期 {anchor.isoformat()} 补全年份/相对日期；" if inferred else ""
        )
        + f"{expression} 表示 {day.isoformat()} 00:00 前（{settings['timezone']}），保存前可修改",
        "basis": {
            "kind": "calendar_boundary",
            "expression": expression,
            "reference_date": anchor.isoformat() if inferred else None,
            "timezone": settings["timezone"],
        },
    }


def resolve_deadline(settings, expression, reference_time=None):
    academic = resolve_academic_deadline(settings, expression)
    if academic["resolved"]:
        return academic
    return resolve_calendar_deadline(settings, expression, reference_time)


def suggest_assignment_deadlines(payload, settings, reference_time=None):
    result = deepcopy(payload)
    for item in result["items"]:
        if item.get("due_at"):
            continue
        proposal = resolve_deadline(settings, item.get("due_text"), reference_time)
        if proposal["resolved"]:
            item["due_at"] = proposal["due_at"]
            item["deadline_basis"] = proposal["basis"]
            item["uncertain_fields"] = [
                f for f in item.get("uncertain_fields", []) if f != "due_at"
            ]
    return result


def validate_deadline_basis(item, settings):
    basis = item.get("deadline_basis")
    if not basis:
        return
    proposal = resolve_deadline(
        settings, basis["expression"], basis.get("reference_date")
    )
    if (
        not proposal["resolved"]
        or basis != proposal["basis"]
        or not item.get("due_at")
        or datetime.fromisoformat(item["due_at"])
        != datetime.fromisoformat(proposal["due_at"])
    ):
        raise HTTPException(
            409,
            "日期或推算依据已变更，请重新告诉助手截止日期或清除推算后校对",
        )
