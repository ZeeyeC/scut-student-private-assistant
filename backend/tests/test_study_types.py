from copy import deepcopy

import pytest

from app import planner
from app.planner import build_plan, instant
from tests.test_foundation import make_client, register_login
from tests.test_person_a_delivery import personal
from tests.test_planning_workbench import preferred_input
from tests.test_scheduling_constraints import seed_work, write


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(planner, "now", lambda: instant("2026-10-14T08:00:00+08:00"))


def typed(p, task_type):
    p = personal(
        deepcopy(p),
        preferred_study_windows=[
            {"weekdays": [3], "start": "16:00", "end": "17:00", "task_type": "deep"},
            {"weekdays": [3], "start": "10:00", "end": "11:00", "task_type": "review"},
        ],
    )
    p["study_classifications"] = {
        "task": {
            "t1": {"task_type": task_type, "difficulty": "high", "confirmed": True}
        },
        "course": {},
    }
    p["planning_strategy"] = "preferred"
    return p


def test_confirmed_work_type_selects_only_matching_preference_and_unknown_is_not_guessed():
    for kind, start in [("deep", "16:00"), ("review", "10:00"), ("unknown", "09:00")]:
        result = build_plan(typed(preferred_input(), kind))
        assert instant(result["blocks"][0]["starts_at"]) == instant(
            f"2026-10-14T{start}:00+08:00"
        )


def test_difficulty_breaks_ties_without_overriding_earlier_deadline():
    p = preferred_input()
    p["constraints"] = []
    p["tasks"].append({"id": "t2", "data": deepcopy(p["tasks"][0]["data"])})
    p["steps"].append(
        {"id": "z", "data": {**deepcopy(p["steps"][0]["data"]), "task_id": "t2"}}
    )
    p["study_classifications"] = {
        "task": {"t1": {"difficulty": "low"}, "t2": {"difficulty": "high"}}
    }
    assert build_plan(p)["blocks"][0]["task_id"] == "t2"
    p["tasks"][0]["data"]["due_at"] = "2026-10-14T10:30:00+08:00"
    assert build_plan(p)["blocks"][0]["task_id"] == "t1"


def test_explicit_types_persist_and_invalidate_plans_without_changing_task_facts(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        task = c.get("/api/tasks").json()[0]
        before = c.get("/api/settings").json()["revision"]
        draft = write(c, h, "/plan-drafts", {}).json()
        body = {
            "revision": 0,
            "target_revision": task["revision"],
            "task_type": "deep",
            "difficulty": "high",
        }
        result = write(
            c, h, f"/study-types/task/{task['id']}", body, "PUT", key="typed"
        )
        assert result.status_code == 200, result.text
        assert (
            write(
                c, h, f"/study-types/task/{task['id']}", body, "PUT", key="typed"
            ).json()
            == result.json()
        )
        assert c.get("/api/tasks/" + task["id"]).json() == task
        assert c.get("/api/settings").json()["revision"] == before + 1
        assert (
            write(
                c, h, f"/drafts/{draft['id']}/confirm", {"revision": draft["revision"]}
            ).status_code
            == 409
        )
        listing = c.get("/api/study-types").json()
        entry = next(
            row for row in listing["items"] if row["target"]["id"] == task["id"]
        )
        assert entry["classification"]["data"]["task_type"] == "deep"
        assert entry["classification"]["data"]["source"] == "user"
        c.post("/api/auth/logout", headers=h)
        other = register_login(c, "other@example.com")
        assert (
            write(c, other, f"/study-types/task/{task['id']}", body, "PUT").status_code
            == 404
        )


def test_course_type_rules_only_generate_for_confirmed_matching_courses(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        course = c.get("/api/courses").json()[0]
        body = {
            "confirmed": True,
            "target_date": "2026-10-14",
            "horizon_days": 1,
            "course_type_rules": [
                {"course_type": "lab", "preparation_minutes": 20, "review_minutes": 0}
            ],
        }
        unknown = write(c, h, "/daily-routine-preview", body)
        assert unknown.status_code == 200, unknown.text
        assert not [
            x for x in unknown.json()["candidates"] if x["kind"] == "preparation"
        ]
        saved = write(
            c,
            h,
            f"/study-types/course/{course['id']}",
            {
                "revision": 0,
                "target_revision": course["revision"],
                "course_type": "lab",
            },
            "PUT",
        )
        assert saved.status_code == 200, saved.text
        preview = write(c, h, "/daily-routine-preview", body).json()
        prep = [x for x in preview["candidates"] if x["kind"] == "preparation"]
        assert len(prep) == 1
        assert (
            instant(prep[0]["ends_at"]) - instant(prep[0]["starts_at"])
        ).total_seconds() == 1200
        assert prep[0]["basis"]["course_type"] == "lab"
        assert c.get("/api/fixed-events").json() == []


def test_type_metadata_rejects_inapplicable_or_stale_input(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        seed_work(c, h)
        course = c.get("/api/courses").json()[0]
        path = f"/study-types/course/{course['id']}"
        assert (
            write(
                c,
                h,
                path,
                {
                    "revision": 0,
                    "target_revision": course["revision"],
                    "task_type": "deep",
                },
                "PUT",
            ).status_code
            == 422
        )
        valid = {
            "revision": 0,
            "target_revision": course["revision"],
            "course_type": "lab",
        }
        saved = write(c, h, path, valid, "PUT").json()
        assert write(c, h, path, valid, "PUT").status_code == 409
        reset = write(
            c,
            h,
            path,
            {
                "revision": saved["revision"],
                "target_revision": course["revision"],
                "course_type": "unknown",
            },
            "PUT",
        )
        assert reset.status_code == 200
        assert reset.json()["data"]["course_type"] == "unknown"
