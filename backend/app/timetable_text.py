"""Conversation course drafts share the reviewed image import save path.

The model only proposes fields. Raw messages come from the server run context,
and only explicit review can turn a candidate into a persisted course.
"""

from copy import deepcopy
from typing import Annotated
from uuid import uuid4

from fastapi import HTTPException
from pydantic import Field

from app import imports, store
from app.calendar import parse_week_expression
from app.campus_presets import effective_settings
from app.contracts import StrictModel
from app.timetable_contracts import TimetableCandidate


class TextCourseFields(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    teacher: str | None = Field(default=None, max_length=200)
    campus: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    weekday: int | None = Field(default=None, ge=1, le=7)
    weeks_text: str | None = Field(default=None, max_length=400)
    periods: list[Annotated[int, Field(strict=True, ge=1, le=30)]] = Field(
        default_factory=list, max_length=30
    )


def candidate_fields(course):
    values = course.model_dump(mode="json")
    for key in ("name", "teacher", "campus", "location", "weeks_text"):
        values[key] = (values[key] or "").strip() or None
    if any(isinstance(p, bool) or p < 1 or p > 30 for p in values["periods"]):
        raise ValueError("节次范围为 1..30")
    values["periods"] = sorted(set(values["periods"]))
    return TimetableCandidate(**values).model_dump(mode="json")


def questions(payload, settings):
    result = []
    if not payload["semester_label"].strip():
        result.append({"field": "semester_label", "question": "这些课程属于哪个学期？"})
    if not settings.get("week1_monday"):
        result.append(
            {
                "field": "week1_monday",
                "question": "请在设置中补充本学期第一周的周一日期。",
            }
        )
    for c in payload["candidates"]:
        if c["excluded"]:
            continue
        label = c["name"] or "这门课"
        missing = {}
        if not c["name"]:
            missing["name"] = "这门课叫什么名字？"
        if not c["weekday"]:
            missing["weekday"] = f"{label}每周星期几上课？"
        try:
            parse_week_expression(c["weeks_text"] or "", settings["week_count"])
        except ValueError:
            missing["weeks_text"] = f"{label}第几周开始、第几周结束？是否分单双周？"
        if not c["periods"]:
            missing["periods"] = f"{label}上第几节到第几节？"
        elif any(
            str(p) not in {str(k) for k in settings["periods"]} for p in c["periods"]
        ):
            missing["periods"] = f"请先在设置中补齐{label}所用节次的起止时间。"
        result.extend(
            {"candidate_id": c["candidate_id"], "field": k, "question": v}
            for k, v in missing.items()
        )
    return result


async def view(db, owner, draft):
    settings = await store.settings(db, owner)
    result = store.view(draft)
    result["data"] = {
        **result["data"],
        "clarifications": questions(
            draft.data["payload"],
            effective_settings(settings.data, draft.data["payload"]),
        ),
    }
    return result


async def create(db, owner, courses, semester_label, context):
    if not 1 <= len(courses) <= 50:
        raise ValueError("每次可添加 1 至 50 条课程候选")
    settings = await store.settings(db, owner)
    payload = {
        "semester_label": semester_label
        if semester_label is not None
        else settings.data["semester_name"],
        "candidates": [
            {
                **candidate_fields(c),
                "candidate_id": str(uuid4()),
                "reviewed": False,
                "excluded": False,
            }
            for c in courses
        ],
    }
    created = await imports.create_draft(
        db,
        owner,
        "timetable_text",
        payload,
        {
            "kind": "conversation",
            "thread_id": context["thread_id"],
            "messages": [{"run_id": context["run_id"], "text": context["message"]}],
        },
    )
    return await view(db, owner, await store.owned(db, owner, created["id"], "draft"))


async def update(
    db, owner, draft_id, revision, candidate_id, changes, semester_label, context
):
    draft = await store.owned(db, owner, draft_id, "draft")
    store.revision(draft, revision)
    if (
        draft.data["draft_kind"] != "timetable_text"
        or draft.data["status"] != "pending"
    ):
        raise HTTPException(
            409, "只能补充尚未保存的文字课表草稿；已有正式课程不会被修改"
        )
    payload = deepcopy(draft.data["payload"])
    patch = changes.model_dump(mode="json", exclude_unset=True)
    if patch:
        selected = next(
            (c for c in payload["candidates"] if c["candidate_id"] == candidate_id),
            None,
        )
        if selected is None:
            raise HTTPException(422, "请先查询草稿，选择真实课程候选标识")
        fields = {k: selected[k] for k in TextCourseFields.model_fields}
        normalized = candidate_fields(TextCourseFields(**{**fields, **patch}))
        selected.update(normalized, reviewed=False)
    if semester_label is not None:
        payload["semester_label"] = semester_label
    if not patch and semester_label is None:
        raise HTTPException(422, "请提供需要补充的课程字段或学期")
    payload["semester_confirmed"] = False
    await imports.edit_draft(db, owner, draft_id, revision, payload)
    source = deepcopy(draft.data["source"])
    if not any(m["run_id"] == context["run_id"] for m in source["messages"]):
        source["messages"].append(
            {"run_id": context["run_id"], "text": context["message"]}
        )
    draft.data = {**draft.data, "source": source}
    return await view(db, owner, draft)
