import re
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
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
    # Equivalent, explicit range separators commonly preserved in chat input.
    # Match the whole numeric range; qualifiers such as “左右” remain invalid.
    clean = re.sub(r"第?(\d+)周?(?:至|到|—|–|～|-)(?:第)?(\d+)", r"\1-\2", clean)
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


COURSE_INTERVAL_VERSION = "course-intervals-1"


def course_intervals(settings, course, day):
    """Keep teaching, protected breaks and nonconsecutive free gaps distinct."""
    tz = ZoneInfo(settings["timezone"])
    teaching, breaks, occupied = [], [], []
    previous = None
    for number in sorted(set(course["periods"])):
        window = settings["periods"].get(str(number)) or settings["periods"].get(number)
        if not window:
            raise ValueError(f"课程 {course['name']} 缺少节次时间映射")
        a, b = time.fromisoformat(window["start"]), time.fromisoformat(window["end"])
        if a.tzinfo or b.tzinfo or b <= a:
            raise ValueError("节次必须使用当地时间，且结束晚于开始")
        if previous and a < previous[2]:
            raise ValueError("所用节次时间重叠或顺序不正确，请核对设置")
        interval = {
            "periods": [number],
            "starts_at": datetime.combine(day, a, tz).isoformat(),
            "ends_at": datetime.combine(day, b, tz).isoformat(),
        }
        teaching.append(interval)
        if previous and number == previous[0] + 1:
            if a > previous[2]:
                breaks.append(
                    {
                        "after_period": previous[0],
                        "before_period": number,
                        "starts_at": datetime.combine(day, previous[2], tz).isoformat(),
                        "ends_at": interval["starts_at"],
                        "protected": True,
                    }
                )
            occupied[-1] = {
                **occupied[-1],
                "periods": [*occupied[-1]["periods"], number],
                "ends_at": interval["ends_at"],
            }
        else:
            occupied.append(dict(interval))
        previous = (number, a, b)
    if not teaching:
        raise ValueError("课程节次不能为空")
    return {
        "interval_version": COURSE_INTERVAL_VERSION,
        "teaching_intervals": teaching,
        "break_intervals": breaks,
        "occupied_intervals": occupied,
    }


def occupied_course_events(occurrences):
    """Scheduling/reminders consume occupied runs, never a whole-day envelope.

    The original occurrence ID remains stable. Additional runs have stable IDs
    derived from their first period; adjacent breaks remain protected inside runs.
    Legacy callers without interval metadata retain their original semantics.
    """
    result = []
    for event in occurrences:
        if event.get("occurrence_id") and event.get("segment_id"):
            result.append(event)
            continue
        intervals = event.get("occupied_intervals")
        if intervals is None:
            result.append(event)
            continue
        for i, interval in enumerate(intervals):
            segment_id = (
                "period-" + str(interval["periods"][0])
                if interval["periods"]
                else "explicit"
            )
            a, b = interval["starts_at"], interval["ends_at"]
            result.append(
                {
                    **event,
                    "id": event["id"] if i == 0 else f"{event['id']}:{segment_id}",
                    "occurrence_id": event["id"],
                    "segment_id": segment_id,
                    "occurrence_starts_at": event["starts_at"],
                    "occurrence_ends_at": event["ends_at"],
                    "starts_at": a,
                    "ends_at": b,
                    "periods": interval["periods"],
                    "teaching_intervals": [
                        x
                        for x in event["teaching_intervals"]
                        if a <= x["starts_at"] and x["ends_at"] <= b
                    ],
                    "break_intervals": [
                        x
                        for x in event["break_intervals"]
                        if a <= x["starts_at"] and x["ends_at"] <= b
                    ],
                }
            )
    return result


def expand_calendar(settings, courses, exceptions, start, end):
    if not courses:
        return []
    if not settings.get("week1_monday"):
        raise ValueError("请配置学期第一周周一")
    anchor = date.fromisoformat(settings["week1_monday"])
    tz = ZoneInfo(settings["timezone"])
    result = []
    lower = datetime.combine(start, time.min, tz).astimezone(timezone.utc)
    upper = datetime.combine(end + timedelta(days=1), time.min, tz).astimezone(
        timezone.utc
    )
    for course in courses:
        c, cid = course["data"], course["id"]
        for week in c["weeks"]:
            if week > settings["week_count"]:
                raise ValueError("课程周次超出学期范围")
            d = anchor + timedelta(weeks=week - 1, days=c["weekday"] - 1)
            ex = next(
                (
                    e
                    for e in reversed(exceptions)
                    if e.get("active", True)
                    and e["course_id"] == cid
                    and e["date"] == d.isoformat()
                ),
                None,
            )
            if ex and ex.get("cancelled"):
                continue
            source = ex.get("source", {}) if ex else {}
            snapshot = (
                source.get("interval_snapshot")
                if source.get("kind") == "semester_calendar"
                and source.get("preserve_periods")
                else None
            )
            # Confirmed makeup intervals are explicit immutable facts. Consume
            # them before reading a subsequently changed period-clock mapping.
            intervals = (
                deepcopy(snapshot) if snapshot else course_intervals(settings, c, d)
            )
            starts = datetime.fromisoformat(
                intervals["teaching_intervals"][0]["starts_at"]
            )
            ends = datetime.fromisoformat(
                intervals["teaching_intervals"][-1]["ends_at"]
            )
            if ex and ex.get("starts_at"):
                moved_start, moved_end = (
                    datetime.fromisoformat(ex["starts_at"]),
                    datetime.fromisoformat(ex["ends_at"]),
                )
                source = ex.get("source", {})
                if source.get("kind") == "semester_calendar" and source.get(
                    "preserve_periods"
                ):
                    from app.constraints import local_instant

                    target = moved_start.astimezone(
                        ZoneInfo(source.get("timezone") or settings["timezone"])
                    ).date()
                    if (
                        source.get("original_date", d.isoformat()) != d.isoformat()
                        or source.get("target_date", target.isoformat())
                        != target.isoformat()
                    ):
                        raise ValueError("校历映射的原日期或目标日期与课程发生不一致")
                    if not snapshot:
                        intervals = course_intervals(settings, c, target)
                        for group in (
                            "teaching_intervals",
                            "break_intervals",
                            "occupied_intervals",
                        ):
                            for part in intervals[group]:
                                for key in ("starts_at", "ends_at"):
                                    local = datetime.fromisoformat(part[key]).replace(
                                        tzinfo=None
                                    )
                                    part[key] = local_instant(local, tz).isoformat()
                    else:
                        if intervals.get("interval_version") != COURSE_INTERVAL_VERSION:
                            raise ValueError("补课分段快照版本不受支持，请核对课程调整")
                        for group in (
                            "teaching_intervals",
                            "break_intervals",
                            "occupied_intervals",
                        ):
                            for part in intervals[group]:
                                a, b = (
                                    datetime.fromisoformat(part[key])
                                    for key in ("starts_at", "ends_at")
                                )
                                if (
                                    a.utcoffset() is None
                                    or b.utcoffset() is None
                                    or not moved_start <= a < b <= moved_end
                                ):
                                    raise ValueError("补课分段快照超出已确认时间")
                    expected_start = datetime.fromisoformat(
                        intervals["teaching_intervals"][0]["starts_at"]
                    )
                    expected_end = datetime.fromisoformat(
                        intervals["teaching_intervals"][-1]["ends_at"]
                    )
                    if moved_start.astimezone(
                        timezone.utc
                    ) != expected_start.astimezone(
                        timezone.utc
                    ) or moved_end.astimezone(timezone.utc) != expected_end.astimezone(
                        timezone.utc
                    ):
                        raise ValueError(
                            "保留节次的校历映射只能改变日期，修改钟点请使用单次调课"
                        )
                # Changing only the room does not destroy known period structure.
                # A new explicit interval is authoritative; never invent breaks.
                elif moved_start != starts or moved_end != ends:
                    interval = {
                        "periods": [],
                        "starts_at": moved_start.isoformat(),
                        "ends_at": moved_end.isoformat(),
                    }
                    intervals = {
                        "interval_version": COURSE_INTERVAL_VERSION,
                        "teaching_intervals": [interval],
                        "break_intervals": [],
                        "occupied_intervals": [interval],
                    }
                starts, ends = moved_start, moved_end
            if (
                starts.astimezone(timezone.utc) < upper
                and ends.astimezone(timezone.utc) > lower
            ):
                result.append(
                    {
                        "id": f"{cid}:{d}",
                        "course_id": cid,
                        "original_date": d.isoformat(),
                        "adjusted": bool(ex),
                        **intervals,
                        "title": c["name"],
                        "campus": (ex.get("campus") or None)
                        if ex and "campus" in ex
                        else (
                            None
                            if ex
                            and ex.get("location") not in (None, c.get("location"))
                            else c.get("campus")
                        ),
                        "starts_at": starts.isoformat(),
                        "ends_at": ends.isoformat(),
                        "location": ex.get("location")
                        if ex and ex.get("location") is not None
                        else c.get("location"),
                    }
                )
    return sorted(
        result, key=lambda x: (datetime.fromisoformat(x["starts_at"]), x["id"])
    )
