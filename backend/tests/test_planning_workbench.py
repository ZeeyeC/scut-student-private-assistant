"""All rules below are explicit synthetic inputs; no B profile or goal service."""

from copy import deepcopy

from app import planner
from app.planner import build_plan, instant
from app.planning_options import compare_plans, risk_report
from tests.test_foundation import make_client, register_login
from tests.test_planner import fixture
from tests.test_scheduling_constraints import (
    confirm,
    protected,
    resources,
    seed_work,
    write,
)


def preferred_input():
    p = fixture()
    p["now_utc"] = instant("2026-10-14T08:00:00+08:00")
    p["occurrences"] = []
    p["steps"] = p["steps"][:1]
    p["steps"][0]["data"]["estimated_minutes"] = 60
    p["constraints"] = [
        protected(
            strength="soft",
            starts_at="2026-10-14T16:00:00+08:00",
            ends_at="2026-10-14T17:00:00+08:00",
        )
    ]
    return p


def test_soft_preference_changes_order_and_explanation_without_decreasing_capacity():
    p = preferred_input()
    before = deepcopy(p)
    result = compare_plans(p)
    early, preferred = result.options
    assert early.preferred_minutes == 0 and preferred.preferred_minutes == 60
    assert instant(early.blocks[0].starts_at) == instant("2026-10-14T09:00:00+08:00")
    assert instant(preferred.blocks[0].starts_at) == instant(
        "2026-10-14T16:00:00+08:00"
    )
    assert early.unallocated_minutes == preferred.unallocated_minutes == 0
    assert early.proposed_minutes == preferred.proposed_minutes == 60
    assert p == before
    p["planning_strategy"] = "preferred"
    r = build_plan(p)
    assert "优先使用已确认软偏好窗口" in r["blocks"][0]["explanation"]["reasons"]


def test_soft_overlaps_do_not_double_count_and_never_override_hard_or_deadlines():
    p = preferred_input()
    p["constraints"] += deepcopy(p["constraints"])
    p["constraints"].append(
        protected(
            strength="hard",
            starts_at="2026-10-14T16:00:00+08:00",
            ends_at="2026-10-14T16:30:00+08:00",
        )
    )
    o = compare_plans(p).options[1]
    assert o.preferred_minutes == 30
    assert all(
        instant(b.ends_at) <= instant("2026-10-14T16:00:00+08:00")
        or instant(b.starts_at) >= instant("2026-10-14T16:30:00+08:00")
        for b in o.blocks
    )
    p["tasks"][0]["data"]["due_at"] = "2026-10-14T12:00:00+08:00"
    o = compare_plans(p).options[1]
    assert o.preferred_minutes == 0 and o.unallocated_minutes == 0
    assert all(
        instant(b.ends_at) <= instant("2026-10-14T12:00:00+08:00") for b in o.blocks
    )


def test_unknown_and_overdue_risks_are_not_zero_actual_effort():
    p = preferred_input()
    p["tasks"][0]["data"]["due_at"] = "2026-10-13T12:00:00+08:00"
    r = risk_report(p, build_plan(p))
    assert r.risks[0].code == "overdue"
    p["steps"] = []
    r = risk_report(p, build_plan(p))
    assert r.unknown_estimate_count == 1 and r.risks[0].remaining_minutes is None


def test_weekly_soft_validity_and_no_profile_produces_honest_identical_options():
    p = preferred_input()
    p["constraints"][0]["data"].update(
        recurrence="weekly",
        weekdays=[3],
        valid_until="2026-10-07",
        starts_at="2026-10-07T16:00:00+08:00",
        ends_at="2026-10-07T17:00:00+08:00",
    )
    r = compare_plans(p)
    assert r.preference_count == 0 and r.options[0].blocks == r.options[1].blocks
    assert r.profile_integration == "pending_person_b"


def setup_client(tmp_path, monkeypatch):
    monkeypatch.setattr(planner, "now", lambda: instant("2026-10-14T08:00:00+08:00"))
    return make_client(tmp_path)


def test_options_and_risks_readonly_soft_confirm_generation_and_stale_guard(
    tmp_path, monkeypatch
):
    with setup_client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        seed_work(c, h)
        d = write(
            c,
            h,
            "/drafts/scheduling-constraint",
            {
                "constraint": {
                    "title": "下午偏好",
                    "strength": "soft",
                    "timezone": "Asia/Shanghai",
                    "starts_at": "2026-10-14T16:00:00+08:00",
                    "ends_at": "2026-10-14T17:00:00+08:00",
                }
            },
        ).json()
        assert confirm(c, h, d).status_code == 200
        olddraft = write(c, h, "/plan-drafts", {}).json()
        before = c.get("/api/data-export").json()["resources"]
        options = c.get("/api/planning-options").json()
        assert len(options["options"]) == 2
        assert c.get("/api/planning-risks").status_code == 200
        assert c.get("/api/data-export").json()["resources"] == before
        assert (
            c.get("/api/drafts/" + olddraft["id"]).json()["data"]["status"] == "pending"
        )
        draft = write(
            c,
            h,
            "/plan-drafts",
            {
                "strategy": "preferred",
                "expected_source_revision": options["source_revision"],
            },
        ).json()
        assert draft["data"]["payload"]["planning_strategy"] == "preferred"
        assert confirm(c, h, draft).status_code == 200
        assert (
            write(
                c,
                h,
                "/plan-drafts",
                {
                    "strategy": "preferred",
                    "expected_source_revision": options["source_revision"],
                },
            ).status_code
            == 409
        )
        assert c.get("/api/planning-options?horizon_days=8").status_code == 422


def test_routines_no_guesses_readonly_durable_dismiss_and_review_save(
    tmp_path, monkeypatch
):
    with setup_client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        c.get("/api/settings")
        before = c.get("/api/data-export").json()["resources"]
        empty = write(c, h, "/daily-routine-preview", {"confirmed": True}).json()
        assert not empty["candidates"] and "未提供明确" in empty["warnings"][0]
        assert c.get("/api/data-export").json()["resources"] == before
        body = {
            "confirmed": True,
            "horizon_days": 1,
            "daily_windows": [{"title": "明确午休", "start": "12:00", "end": "12:30"}],
        }
        p = write(c, h, "/daily-routine-preview", body).json()
        candidate = p["candidates"][0]
        assert candidate["can_add"]
        args = {
            "request": body,
            "candidate_id": candidate["id"],
            "expected_source_revision": p["source_revision"],
        }
        assert write(c, h, "/daily-routine-dismiss", args).status_code == 200
        p2 = write(c, h, "/daily-routine-preview", body).json()
        assert p2["candidates"][0]["dismissed"] and not p2["candidates"][0]["can_add"]
        assert write(c, h, "/daily-routine-drafts", args).status_code == 409
        body["daily_windows"][0]["title"] = "明确休息"
        p = write(c, h, "/daily-routine-preview", body).json()
        args.update(
            request=body,
            candidate_id=p["candidates"][0]["id"],
            expected_source_revision=p["source_revision"],
        )
        d = write(c, h, "/daily-routine-drafts", args).json()
        assert write(c, h, "/daily-routine-drafts", args).json()["id"] == d["id"]
        assert not c.get("/api/fixed-events").json()
        assert confirm(c, h, d).status_code == 200
        assert len(c.get("/api/fixed-events").json()) == 1
        assert not write(c, h, "/daily-routine-preview", body).json()["candidates"][0][
            "can_add"
        ]
        assert (
            resources(c, "routine_dismissal")[0]["data"]["candidate_id"]
            == candidate["id"]
        )
    with make_client(tmp_path) as c2:
        c2.cookies.update(c.cookies)
        body["daily_windows"][0]["title"] = "明确午休"
        assert write(c2, h, "/daily-routine-preview", body).json()["candidates"][0][
            "dismissed"
        ]


def test_course_preparation_review_conflicts_and_unknown_transfers(
    tmp_path, monkeypatch
):
    with setup_client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        seed_work(c, h)
        p = write(
            c,
            h,
            "/daily-routine-preview",
            {
                "confirmed": True,
                "horizon_days": 1,
                "preparation_minutes": 15,
                "review_minutes": 20,
                "include_campus_transfer": True,
            },
        ).json()
        assert {r["kind"] for r in p["candidates"]} == {"preparation", "review"}
        assert all(r["can_add"] for r in p["candidates"])
        assert instant(p["candidates"][0]["ends_at"]) == instant(
            "2026-10-14T09:00:00+08:00"
        )
        assert instant(p["candidates"][1]["starts_at"]) == instant(
            "2026-10-14T10:00:00+08:00"
        )
        write(
            c,
            h,
            "/fixed-events",
            {
                "title": "真实固定冲突",
                "starts_at": "2026-10-14T08:30:00+08:00",
                "ends_at": "2026-10-14T09:00:00+08:00",
            },
        )
        p = write(
            c,
            h,
            "/daily-routine-preview",
            {"confirmed": True, "horizon_days": 1, "preparation_minutes": 15},
        ).json()
        assert not p["candidates"][0]["can_add"] and p["candidates"][0]["conflicts"]
        assert (
            write(c, h, "/daily-routine-preview", {"confirmed": False}).status_code
            == 422
        )
        assert (
            write(
                c,
                h,
                "/daily-routine-preview",
                {
                    "confirmed": True,
                    "daily_windows": [
                        {"title": "错误", "start": "13:00", "end": "12:00"}
                    ],
                },
            ).status_code
            == 422
        )


def test_commute_uses_only_confirmed_directional_time_and_flags_insufficient_gap(
    tmp_path, monkeypatch
):
    with setup_client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        seed_work(c, h)
        settings = c.get("/api/settings").json()
        settings["data"]["periods"]["2"] = {"start": "11:00", "end": "12:00"}
        settings["data"]["campus_transfers"] = [
            {"from_campus": "A", "to_campus": "B", "minutes": 40}
        ]
        assert write(c, h, "/settings", settings, "PUT").status_code == 200
        d = write(
            c,
            h,
            "/drafts/timetable",
            {
                "semester_label": "合成跨区",
                "courses": [
                    {
                        "source_key": "math",
                        "name": "高数",
                        "weekday": 3,
                        "weeks": [1],
                        "periods": [1],
                        "campus": "A",
                    },
                    {
                        "source_key": "next",
                        "name": "实验",
                        "weekday": 3,
                        "weeks": [1],
                        "periods": [2],
                        "campus": "B",
                    },
                ],
            },
        ).json()
        assert confirm(c, h, d).status_code == 200
        request = {
            "confirmed": True,
            "horizon_days": 1,
            "include_campus_transfer": True,
        }
        p = write(c, h, "/daily-routine-preview", request).json()
        commute = p["candidates"][0]
        assert commute["kind"] == "commute" and commute["can_add"]
        assert instant(commute["starts_at"]) == instant("2026-10-14T10:20:00+08:00")
        settings = c.get("/api/settings").json()
        settings["data"]["campus_transfers"][0]["minutes"] = 80
        assert write(c, h, "/settings", settings, "PUT").status_code == 200
        p = write(c, h, "/daily-routine-preview", request).json()
        assert not p["candidates"][0]["can_add"]
        settings = c.get("/api/settings").json()
        settings["data"]["campus_transfers"] = []
        assert write(c, h, "/settings", settings, "PUT").status_code == 200
        p = write(c, h, "/daily-routine-preview", request).json()
        assert not p["candidates"] and "未确认转移时长" in p["warnings"][0]


def test_routine_stale_cross_user_and_delete_export_boundaries(tmp_path, monkeypatch):
    with setup_client(tmp_path, monkeypatch) as c:
        h = register_login(c)
        body = {
            "confirmed": True,
            "horizon_days": 1,
            "daily_windows": [{"title": "休息", "start": "12:00", "end": "12:30"}],
        }
        p = write(c, h, "/daily-routine-preview", body).json()
        args = {
            "request": body,
            "candidate_id": p["candidates"][0]["id"],
            "expected_source_revision": p["source_revision"],
        }
        write(
            c,
            h,
            "/fixed-events",
            {
                "title": "新事实",
                "starts_at": "2026-10-14T12:00:00+08:00",
                "ends_at": "2026-10-14T12:30:00+08:00",
            },
        )
        assert write(c, h, "/daily-routine-drafts", args).status_code == 409
        p = write(c, h, "/daily-routine-preview", body).json()
        args["expected_source_revision"] = p["source_revision"]
        assert write(c, h, "/daily-routine-dismiss", args).status_code == 200
        assert len(resources(c, "routine_dismissal")) == 1
        c.cookies.clear()
        other = register_login(c, "other@example.com")
        other_preview = write(c, other, "/daily-routine-preview", body).json()
        assert not other_preview["candidates"][0]["dismissed"]
        assert not resources(c, "routine_dismissal")


def test_preference_fragmentation_gives_way_instead_of_stranding_feasible_work():
    p = preferred_input()
    p["settings"]["study_windows"] = [{"start": "09:00", "end": "10:00"}]
    p["constraints"][0]["data"].update(
        starts_at="2026-10-14T09:10:00+08:00", ends_at="2026-10-14T09:20:00+08:00"
    )
    p["planning_strategy"] = "preferred"
    before = deepcopy(p)
    result = build_plan(p)
    assert result["capacity"]["proposed_minutes"] == 60
    assert result["capacity"]["unallocated_minutes"] == 0
    assert result["preference_fallback"] is True
    assert "让步" in result["blocks"][0]["explanation"]["reasons"][-1]
    assert p == before
    options = compare_plans(p)
    assert all(o.unallocated_minutes == 0 for o in options.options)
