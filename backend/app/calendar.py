import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def parse_week_expression(text, week_count):
    clean = (
        re.sub(r"\s", "", text)
        .replace("（", "(")
        .replace("）", ")")
        .replace("、", ",")
        .replace("，", ",")
        .replace("－", "-")
        .replace("~", "-")
    )
    result = set()
    group = []
    for part in clean.split(","):
        match = re.fullmatch(r"第?(\d+)(?:-(\d+))?(周)?(?:\(([单双])\))?", part)
        if not match:
            raise ValueError("无法确定周次，请校对")
        a, b = int(match[1]), int(match[2] or match[1])
        if a < 1 or b > week_count or b < a:
            raise ValueError("周次超出学期范围")
        group.extend(range(a, b + 1))
        if match[3] or match[4]:
            parity = 1 if match[4] == "单" else 0 if match[4] == "双" else None
            result.update(w for w in group if parity is None or w % 2 == parity)
            group = []
    result.update(group)
    if not result:
        raise ValueError("周次为空")
    return sorted(result)


def expand_calendar(settings, courses, exceptions, start, end):
    if not courses:
        return []
    if not settings.get("week1_monday"):
        raise ValueError("请配置学期第一周周一")
    anchor = date.fromisoformat(settings["week1_monday"])
    tz = ZoneInfo(settings["timezone"])
    result = []
    for course in courses:
        c, cid = course["data"], course["id"]
        periods = [
            settings["periods"].get(str(p)) or settings["periods"].get(p)
            for p in c["periods"]
        ]
        if not all(periods):
            raise ValueError(f"课程 {c['name']} 缺少节次时间映射")
        for week in c["weeks"]:
            if week > settings["week_count"]:
                raise ValueError("课程周次超出学期范围")
            d = anchor + timedelta(weeks=week - 1, days=c["weekday"] - 1)
            ex = next(
                (
                    e
                    for e in exceptions
                    if e["course_id"] == cid and e["date"] == d.isoformat()
                ),
                None,
            )
            if ex and ex.get("cancelled"):
                continue
            starts = datetime.combine(
                d, min(time.fromisoformat(p["start"]) for p in periods), tz
            )
            ends = datetime.combine(
                d, max(time.fromisoformat(p["end"]) for p in periods), tz
            )
            if ex and ex.get("starts_at"):
                starts, ends = (
                    datetime.fromisoformat(ex["starts_at"]),
                    datetime.fromisoformat(ex["ends_at"]),
                )
            if start <= starts.astimezone(tz).date() <= end:
                result.append(
                    {
                        "id": f"{cid}:{d}",
                        "course_id": cid,
                        "title": c["name"],
                        "starts_at": starts.isoformat(),
                        "ends_at": ends.isoformat(),
                        "location": ex.get("location")
                        if ex and ex.get("location")
                        else c.get("location"),
                    }
                )
    return sorted(result, key=lambda x: (x["starts_at"], x["id"]))
