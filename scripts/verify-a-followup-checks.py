"""Additional assertions run inside the actual frozen A+B verifier harness."""

from datetime import timedelta
from uuid import uuid4


def checks(get, write, task_id, local_day):
    tomorrow = local_day + timedelta(days=1)
    profile = get("/profile")
    write(
        "/profile",
        {
            "revision": profile["revision"],
            "data": {
                "timezone": "Asia/Shanghai",
                "preferences": {
                    "preferred_study_windows": [
                        {
                            "weekdays": list(range(1, 8)),
                            "start": "21:00",
                            "end": "22:00",
                            "task_type": "any",
                        }
                    ],
                    "focus_minutes": 25,
                    "break_minutes": 5,
                    "daily_load_minutes": 180,
                },
            },
        },
        method="PUT",
    )
    cfg = get("/settings")
    cfg["data"].update(
        study_windows=[{"start": "09:00", "end": "22:00"}],
        daily_limit_minutes=180,
        buffer_minutes=0,
    )
    write("/settings", cfg, method="PUT")
    goal = write(
        "/goals",
        {
            "title": "冻结甲方预算",
            "weekly_budget_minutes": 600,
            "priority": 3,
            "load_category": "study",
            "allowed_adjustment": "reduce",
            "subtasks": [
                {
                    "title": "剩余练习",
                    "status": "open",
                    "estimated_minutes": 60,
                    "task_id": task_id,
                }
            ],
        },
    )
    options = get(f"/planning-options?target_date={tomorrow}&horizon_days=1")
    assert options["options"][1]["preferred_minutes"] == 15
    assert options["goal_allocation"]["task_goal_ids"][task_id] == goal["id"]
    assert sum(w["planned_minutes"] for w in options["goal_allocation"]["weeks"]) == 15
    before = get("/plan-blocks")
    notice = write("/replanning/changes", {})["notice"]
    assert write("/replanning/changes", {})["consumed"] == 0
    assert get("/plan-blocks") == before
    draft = write(
        "/replanning/changes/draft",
        {
            "revision": notice["revision"],
            "source_revision": notice["data"]["source_revision"],
        },
    )
    write(f"/drafts/{draft['id']}/confirm", {"revision": draft["revision"]})
    assert get("/replanning/changes")["data"]["state"] == "confirmed"
    assert write("/replanning/changes", {})["consumed"] == 0

    assignment = write(
        "/drafts/assignment",
        {"items": [{"title": "冻结时长生成", "due_at": f"{tomorrow}T23:59:00+08:00"}]},
    )
    tid = write(
        f"/drafts/{assignment['id']}/confirm", {"revision": assignment["revision"]}
    )["saved_ids"][0]
    step_draft = write(
        f"/tasks/{tid}/step-drafts",
        {
            "task_revision": get(f"/tasks/{tid}")["revision"],
            "steps": [
                {
                    "key": "one",
                    "title": "观测步骤",
                    "description": "合成冻结验收",
                    "estimated_minutes": 60,
                    "dependency_keys": [],
                    "acceptance_criteria": ["完成"],
                }
            ],
        },
    )
    write(f"/drafts/{step_draft['id']}/confirm", {"revision": step_draft["revision"]})
    for i in range(3):
        step = get(f"/tasks/{tid}/steps")[0]
        write(
            "/executions",
            {
                "client_operation_id": str(uuid4()),
                "execution_id": str(uuid4()),
                "task_id": tid,
                "task_revision": get(f"/tasks/{tid}")["revision"],
                "step_id": step["id"],
                "step_revision": step["revision"],
                "performed_on": str(local_day),
                "timezone": "Asia/Shanghai",
                "actual_minutes": 25,
                "feedback": "completed" if i == 2 else "partial",
                "task_status": "open",
            },
        )
    result = write(
        "/duration-suggestions/generate",
        {"expected_source_revision": get("/settings")["revision"]},
        key="generate",
    )
    assert len(result["created_ids"]) == 1
    item = next(
        s for s in result["result"]["suggestions"] if s["data"]["task_id"] == tid
    )
    assert item["data"]["suggested_minutes"] == 75 and item["freshness"] == "fresh"
    assert get(f"/tasks/{tid}/steps")[0]["data"]["estimated_minutes"] == 60

    def action(item, verb):
        return write(
            f"/duration-suggestions/{item['id']}/actions",
            {
                "revision": item["revision"],
                "task_revision": item["current_task_revision"],
                "step_revision": item["current_step_revision"],
                "source_revision": item["current_source_revision"],
                "action": verb,
            },
        )

    accepted = action(item, "accept")
    assert accepted["step"]["data"]["estimated_minutes"] == 75
    assert (
        action(accepted["suggestion"], "restore_default")["step"]["data"][
            "estimated_minutes"
        ]
        == 60
    )
    assert (
        write(
            "/duration-suggestions/generate",
            {"expected_source_revision": get("/settings")["revision"]},
        )["created_ids"]
        == []
    )
    return [
        "confirmed-profile-real-preferred-window",
        "single-shared-goal-allocation",
        "events-consumed-once-without-plan-write",
        "notice-original-plan-confirmation-no-loop",
        "real-three-record-duration-generation",
        "generated-advice-does-not-change-step",
        "B-accept-restore-generated-duration",
        "handled-duration-basis-never-reappears",
    ]
