"""Recognition candidates deliberately allow missing fields; Course does not."""

from typing import Literal

from pydantic import Field, model_validator

from app.contracts import StrictModel

TimetableField = Literal[
    "name", "teacher", "campus", "location", "weekday", "weeks_text", "periods"
]


class TimetableEvidence(StrictModel):
    field: TimetableField
    text: str = Field(min_length=1, max_length=4000)
    # Normalized x0,y0,x1,y1 in the rendered page, or explicitly unavailable.
    bbox: list[float] | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="Normalized rectangle [left, top, right, bottom], each 0..1, origin at top left. Never use pixel or 0..1000 coordinates. Use null if unavailable.",
    )
    bbox_note: str | None = Field(default=None, max_length=200)
    page: int = Field(default=1, ge=1, le=10)

    @model_validator(mode="before")
    @classmethod
    def rectangle(cls, value):
        if isinstance(value, dict) and value.get("bbox") is not None:
            box = value["bbox"]
            valid = (
                isinstance(box, list)
                and len(box) == 4
                and all(
                    isinstance(n, (int, float)) and not isinstance(n, bool) for n in box
                )
            )
            if not valid or not (
                0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1
            ):
                # Invalid grounding is never rescaled or guessed. Keep the text
                # evidence and explicitly make this region unavailable.
                return {
                    **value,
                    "bbox": None,
                    "bbox_note": "模型区域无效，已取消定位，请对照原页",
                }
        return value


class TimetableCandidate(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    teacher: str | None = Field(default=None, max_length=200)
    campus: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    weekday: int | None = Field(default=None, ge=1, le=7)
    weeks_text: str | None = Field(default=None, max_length=400)
    periods: list[int] = Field(default_factory=list, max_length=30)
    uncertain_fields: list[TimetableField] = Field(default_factory=list)
    evidence: list[TimetableEvidence] = Field(default_factory=list, max_length=100)


class TimetablePageExtraction(StrictModel):
    semester_label: str | None = Field(default=None, max_length=200)
    candidates: list[TimetableCandidate] = Field(default_factory=list, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=100)


class TimetableReviewCandidate(TimetableCandidate):
    candidate_id: str = Field(min_length=1, max_length=100)
    reviewed: bool = False
    excluded: bool = False


class TimetableRecognition(StrictModel):
    semester_label: str = Field(default="", max_length=200)
    semester_confirmed: bool = False
    candidates: list[TimetableReviewCandidate] = Field(max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("识别候选标识重复")
        return self


class TimetableJobRequest(StrictModel):
    asset_id: str
    consent: Literal[True]
