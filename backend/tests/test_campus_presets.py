from copy import deepcopy
from uuid import uuid4

import pytest

from app import imports
from app.timetable_recognition import merge_pages
from tests.test_assignments import png
from tests.test_conflicts import preview, timetable
from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import confirm, write
from tests.test_timetable_recognition import (
    FakeTimetableVision,
    candidate,
    edit,
    recognize,
    reviewed,
    upload,
)

WUSHAN_EXPECTED = {
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

GUOJI_DAXUECHENG_EXPECTED = {
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


def normalize_periods(periods):
    return {
        str(k): {"start": v["start"][:5], "end": v["end"][:5]}
        for k, v in periods.items()
    }


def test_trusted_campus_presets_endpoint_and_exact_templates(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        r = c.get("/api/campus-presets", headers=h)
        assert r.status_code == 200, r.text
        presets = r.json()
        assert [p["id"] for p in presets] == ["wushan", "guoji", "daxuecheng"]
        assert [p["label"] for p in presets] == ["五山", "国际", "大学城"]
        assert normalize_periods(presets[0]["periods"]) == WUSHAN_EXPECTED
        assert normalize_periods(presets[1]["periods"]) == GUOJI_DAXUECHENG_EXPECTED
        assert normalize_periods(presets[2]["periods"]) == GUOJI_DAXUECHENG_EXPECTED
        assert all(set(p["periods"].keys()) == {str(i) for i in range(1, 13)} for p in presets)
        assert all(p["classroom_open"] == "07:00" for p in presets)
        assert presets[0]["morning_exercise"] == "09:40-10:00"
        assert presets[1]["morning_exercise"] == "10:25-10:40"
        assert presets[2]["morning_exercise"] == "10:25-10:40"


def test_settings_preset_fills_twelve_periods_and_custom_edits_clear_preset(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        s = c.get("/api/settings").json()
        assert s["data"].get("campus_preset") is None
        assert s["data"]["periods"] == {}

        # Selecting guoji in settings fills 12 periods and stores id "guoji"
        s["data"]["campus_preset"] = "guoji"
        r = write(c, h, "/settings", s, "PUT")
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["data"]["campus_preset"] == "guoji"
        assert normalize_periods(saved["data"]["periods"]) == GUOJI_DAXUECHENG_EXPECTED

        # Switching to daxuecheng preserves distinct ID even though times are identical
        saved["data"]["campus_preset"] = "daxuecheng"
        r2 = write(c, h, "/settings", saved, "PUT")
        assert r2.status_code == 200, r2.text
        saved2 = r2.json()
        assert saved2["data"]["campus_preset"] == "daxuecheng"
        assert normalize_periods(saved2["data"]["periods"]) == GUOJI_DAXUECHENG_EXPECTED

        # Custom edit to any period clears campus_preset to None while keeping custom periods
        saved2["data"]["periods"]["1"] = {"start": "08:30", "end": "09:15"}
        r3 = write(c, h, "/settings", saved2, "PUT")
        assert r3.status_code == 200, r3.text
        saved3 = r3.json()
        assert saved3["data"]["campus_preset"] is None
        assert saved3["data"]["periods"]["1"]["start"][:5] == "08:30"
        assert len(saved3["data"]["periods"]) == 12

        # Invalid preset ID rejected with 422 and no write
        bad = deepcopy(saved3)
        bad["data"]["campus_preset"] = "unknown_campus"
        assert write(c, h, "/settings", bad, "PUT").status_code == 422
        assert c.get("/api/settings").json() == saved3


def test_school_timetable_deferred_preset_conflict_preview_atomic_commit_and_cancel(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        s = c.get("/api/settings").json()
        s["data"]["week1_monday"] = "2026-10-12"
        s["data"]["semester_name"] = "2026秋季"
        assert write(c, h, "/settings", s, "PUT").status_code == 200

        # Fixed event 08:10-08:30 on Wednesday 2026-10-14 overlaps Wushan period 1 (08:00-08:45)
        # but does NOT overlap Guoji/Daxuecheng period 1 (08:50-09:35).
        fixed = write(
            c,
            h,
            "/fixed-events",
            {
                "title": "晨间事项",
                "starts_at": "2026-10-14T08:10:00+08:00",
                "ends_at": "2026-10-14T08:30:00+08:00",
            },
        )
        assert fixed.status_code == 200, fixed.text

        d = timetable(
            c,
            h,
            source_key="c1",
            name="线性代数",
            campus="五山",
            location="A101",
            weekday=3,
            weeks=[1],
            periods=[1],
        )

        # Preview with wushan detects overlap using derived settings without writing settings
        wushan_payload = {**d["data"]["payload"], "campus_preset": "wushan"}
        wushan_report = preview(c, h, d, wushan_payload)
        assert wushan_report["complete"] is True
        assert wushan_report["conflict_count"] == 1
        assert wushan_report["issues"][0]["code"] == "overlap"
        assert c.get("/api/settings").json()["data"]["campus_preset"] is None
        assert c.get("/api/settings").json()["data"]["periods"] == {}

        # Preview with guoji vs daxuecheng has 0 conflicts and distinct conflict tokens
        guoji_payload = {**d["data"]["payload"], "campus_preset": "guoji"}
        daxuecheng_payload = {**d["data"]["payload"], "campus_preset": "daxuecheng"}
        guoji_report = preview(c, h, d, guoji_payload)
        daxuecheng_report = preview(c, h, d, daxuecheng_payload)
        assert guoji_report["complete"] is True and guoji_report["conflict_count"] == 0
        assert (
            daxuecheng_report["complete"] is True
            and daxuecheng_report["conflict_count"] == 0
        )
        assert guoji_report["conflict_token"] != daxuecheng_report["conflict_token"]

        # Saving draft payload still does not write settings; cancelling draft does not write settings
        temp = timetable(c, h, source_key="temp", name="临时课")
        temp = write(
            c,
            h,
            f"/drafts/{temp['id']}",
            {
                "revision": temp["revision"],
                "payload": {**temp["data"]["payload"], "campus_preset": "wushan"},
            },
            "PUT",
        ).json()
        assert (
            write(
                c, h, f"/drafts/{temp['id']}", {"revision": temp["revision"]}, "DELETE"
            ).status_code
            == 200
        )
        assert c.get("/api/settings").json()["data"]["campus_preset"] is None
        assert c.get("/api/settings").json()["data"]["periods"] == {}

        # Editing draft to daxuecheng and attempting to confirm with guoji_report token fails 409
        d = write(
            c,
            h,
            f"/drafts/{d['id']}",
            {"revision": d["revision"], "payload": daxuecheng_payload},
            "PUT",
        ).json()
        stale = write(
            c,
            h,
            f"/drafts/{d['id']}/confirm",
            {"revision": d["revision"], "conflict_token": guoji_report["conflict_token"]},
        )
        assert stale.status_code == 409
        assert c.get("/api/settings").json()["data"]["campus_preset"] is None
        assert c.get("/api/courses").json() == []

        # Confirming with matching daxuecheng token atomically commits settings and course
        committed = write(
            c,
            h,
            f"/drafts/{d['id']}/confirm",
            {
                "revision": d["revision"],
                "conflict_token": daxuecheng_report["conflict_token"],
            },
        )
        assert committed.status_code == 200, committed.text
        after_settings = c.get("/api/settings").json()["data"]
        assert after_settings["campus_preset"] == "daxuecheng"
        assert normalize_periods(after_settings["periods"]) == GUOJI_DAXUECHENG_EXPECTED
        courses = c.get("/api/courses").json()
        assert len(courses) == 1
        assert courses[0]["data"]["campus"] == "五山"
        assert courses[0]["data"]["location"] == "A101"
        assert len(c.get("/api/fixed-events").json()) == 1


@pytest.mark.parametrize("kind", ["timetable_recognition", "timetable_text"])
def test_recognition_and_text_reviews_use_effective_preset_and_preserve_custom_settings(
    tmp_path, kind
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        s = c.get("/api/settings").json()
        s["data"].update(semester_name="2026秋季", week1_monday="2026-09-07", periods={})
        assert write(c, h, "/settings", s, "PUT").status_code == 200

        if kind == "timetable_recognition":
            c.app.state.gateway = FakeTimetableVision(
                [candidate(periods=[1, 12], campus="国际", location="D1-101")]
            )
            job = recognize(c, h, upload(c, h, raw=png()))
            d = c.get("/api/drafts/" + job["data"]["draft_id"]).json()
        else:
            import asyncio

            payload = merge_pages(
                [
                    {
                        "semester_label": "2026秋季",
                        "candidates": [
                            candidate(periods=[1, 12], campus="国际", location="D1-101")
                        ],
                        "warnings": [],
                    }
                ],
                20,
            )
            owner = c.get("/api/me").json()["id"]

            async def make_text_draft():
                async with c.app.state.sessions() as db:
                    res = await imports.create_draft(
                        db, str(owner), "timetable_text", payload, {"messages": []}
                    )
                    await db.commit()
                    return res

            d = asyncio.run(make_text_draft())

        base_payload = reviewed(d)
        # Without preset or saved periods, timetable-preview fails 422
        assert (
            write(
                c,
                h,
                f"/drafts/{d['id']}/timetable-preview",
                {"revision": d["revision"], "payload": base_payload},
            ).status_code
            == 422
        )

        # With preset="wushan", timetable-preview and conflict-preview succeed without writing settings
        with_preset = {**base_payload, "campus_preset": "wushan"}
        diff = write(
            c,
            h,
            f"/drafts/{d['id']}/timetable-preview",
            {"revision": d["revision"], "payload": with_preset},
        )
        assert diff.status_code == 200, diff.text
        assert diff.json()["added"] == ["高等数学"]
        report = preview(c, h, d, with_preset)
        assert report["complete"] is True
        assert c.get("/api/settings").json()["data"]["campus_preset"] is None
        assert c.get("/api/settings").json()["data"]["periods"] == {}

        # Error during confirm (e.g. semester mismatch) rolls back and writes nothing
        bad_payload = {**with_preset, "semester_label": "2027春季"}
        d = edit(c, h, d, bad_payload)
        assert confirm(c, h, d).status_code == 422
        assert c.get("/api/settings").json()["data"]["campus_preset"] is None
        assert c.get("/api/courses").json() == []

        # Valid confirm atomically writes wushan preset, 12 periods, and course
        d = edit(c, h, d, with_preset)
        report = preview(c, h, d, with_preset)
        res = write(
            c,
            h,
            f"/drafts/{d['id']}/confirm",
            {"revision": d["revision"], "conflict_token": report["conflict_token"]},
        )
        assert res.status_code == 200, res.text
        saved_settings = c.get("/api/settings").json()["data"]
        assert saved_settings["campus_preset"] == "wushan"
        assert normalize_periods(saved_settings["periods"]) == WUSHAN_EXPECTED
        saved_courses = c.get("/api/courses").json()
        assert len(saved_courses) == 1
        assert saved_courses[0]["data"]["campus"] == "国际"
        assert saved_courses[0]["data"]["location"] == "D1-101"

        # Subsequent draft inherits saved campus_preset="wushan" by default
        next_draft = timetable(c, h, source_key="next-course")
        assert next_draft["data"]["payload"]["campus_preset"] == "wushan"

        # If user customizes periods in settings (campus_preset becomes None), new draft does not overwrite custom periods
        s_now = c.get("/api/settings").json()
        s_now["data"]["campus_preset"] = None
        s_now["data"]["periods"] = {"1": {"start": "09:10", "end": "09:55"}}
        assert write(c, h, "/settings", s_now, "PUT").status_code == 200
        custom_draft = timetable(c, h, source_key="custom-course", periods=[1])
        assert custom_draft["data"]["payload"]["campus_preset"] is None
        custom_report = preview(c, h, custom_draft)
        assert (
            write(
                c,
                h,
                f"/drafts/{custom_draft['id']}/confirm",
                {
                    "revision": custom_draft["revision"],
                    "conflict_token": custom_report["conflict_token"],
                },
            ).status_code
            == 200
        )
        after_custom = c.get("/api/settings").json()["data"]
        assert after_custom["campus_preset"] is None
        assert normalize_periods(after_custom["periods"]) == {
            "1": {"start": "09:10", "end": "09:55"}
        }
