"""Read-only weekly facts and explicit, versioned links to original planner drafts."""

import math
from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import store
from app.db import Resource, now
from app.execution import covered_blocks, effective, legacy_estimates
from app.planning_history import record_change
from app.review_contracts import validate_week

UTC = timezone.utc


def instant(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timestamp needs offset")
    return result.astimezone(UTC)


def bounds(day, zone):
    return datetime.combine(day, time.min, zone).astimezone(UTC), datetime.combine(
        day + timedelta(days=7), time.min, zone
    ).astimezone(UTC)


def overlap(start, end, lower, upper):
    return max(0.0, (min(end, upper) - max(start, lower)).total_seconds())


def block_seconds(block, lower, upper):
    start, end = instant(block["starts_at"]), instant(block["ends_at"])
    if end <= start:
        raise ValueError("invalid plan interval")
    return overlap(start, end, lower, upper)


def plan_projection(snapshots, week, zone, *, latest=False):
    """Earliest/latest approved coverage per local day, never sum whole snapshots."""
    day_texts = [(week + timedelta(days=n)).isoformat() for n in range(7)]
    dates, refs, blocks, gaps = [], set(), {}, set()
    lower, _ = bounds(week, zone)
    for day_text in day_texts:
        candidates = []
        for snapshot in snapshots:
            p = snapshot.data.get("approved_plan", {})
            try:
                start = date.fromisoformat(p["target_date"])
                finish = start + timedelta(days=p["horizon_days"])
                approved = instant(snapshot.data["approved_at"])
                if not start <= date.fromisoformat(day_text) < finish:
                    continue
                if p.get("timezone") != zone.key:
                    gaps.add("snapshot_timezone_mismatch")
                    continue
                candidates.append((approved, snapshot.id, snapshot))
            except (KeyError, ValueError, TypeError, OverflowError):
                gaps.add("invalid_snapshot_scope")
        if not candidates:
            continue
        approved, _, selected = sorted(candidates, key=lambda x: (x[0], x[1]))[
            -1 if latest else 0
        ]
        refs.add(selected.id)
        dates.append(day_text)
        if not latest and approved > lower:
            gaps.add("original_recorded_after_week_start")
        day = date.fromisoformat(day_text)
        lo = datetime.combine(day, time.min, zone).astimezone(UTC)
        hi = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC)
        seen = {}
        for b in selected.data["approved_plan"].get("blocks", []):
            try:
                bid = b["id"]
                if bid in seen:
                    if seen[bid] != b:
                        gaps.add("conflicting_snapshot_block")
                    continue
                seen[bid] = b
                seconds = block_seconds(b, lo, hi)
                if seconds:
                    entry = blocks.setdefault(
                        bid,
                        {
                            "plan_block_id": bid,
                            "task_id": b.get("task_id"),
                            "title": b.get("title", "学习安排"),
                            "seconds": 0,
                            "snapshot_ids": [],
                        },
                    )
                    entry["seconds"] += seconds
                    if selected.id not in entry["snapshot_ids"]:
                        entry["snapshot_ids"].append(selected.id)
            except (KeyError, ValueError, TypeError):
                gaps.add("invalid_snapshot_block")
    status = (
        "missing"
        if not dates
        else "complete"
        if len(dates) == 7 and not gaps
        else "partial"
    )
    total = sum(b["seconds"] for b in blocks.values()) / 60
    return {
        "status": status,
        "minutes": total if status == "complete" else None,
        "known_minutes": total,
        "covered_dates": dates,
        "snapshot_ids": sorted(refs),
        "blocks": list(blocks.values()),
        "gaps": sorted(gaps),
    }


def current_projection(blocks, lower, upper):
    entries, gaps = [], []
    for b in blocks:
        try:
            seconds = block_seconds(b.data, lower, upper)
            if seconds:
                entries.append(
                    {
                        "plan_block_id": b.id,
                        "task_id": b.data.get("task_id"),
                        "title": b.data.get("title", "学习安排"),
                        "seconds": seconds,
                        "snapshot_ids": [],
                    }
                )
        except (KeyError, ValueError, TypeError):
            gaps.append("invalid_current_block")
    total = sum(b["seconds"] for b in entries) / 60
    return {
        "status": "partial" if gaps else "complete",
        "minutes": None if gaps else total,
        "known_minutes": total,
        "covered_dates": [],
        "snapshot_ids": [],
        "blocks": entries,
        "gaps": sorted(set(gaps)),
    }


def manual_membership(data, lower, upper):
    """A date in another zone is an interval, not a guessed midnight instant."""
    try:
        day = date.fromisoformat(data["performed_on"])
        tz = ZoneInfo(data["timezone"])
        lo = datetime.combine(day, time.min, tz).astimezone(UTC)
        hi = datetime.combine(day + timedelta(days=1), time.min, tz).astimezone(UTC)
        if hi <= lower or lo >= upper:
            return "outside"
        return "inside" if lo >= lower and hi <= upper else "ambiguous"
    except (KeyError, ValueError, TypeError):
        return "ambiguous"


def record_seconds(record, timers, lower, upper):
    d = record.data
    membership = manual_membership(d, lower, upper)
    try:
        seconds = (
            d["actual_seconds"] if "actual_seconds" in d else d["actual_minutes"] * 60
        )
        if (
            not isinstance(seconds, (int, float))
            or isinstance(seconds, bool)
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("invalid duration")
        if d.get("source") != "timer":
            return membership, seconds if membership == "inside" else None
        timer = timers.get(d.get("timer_id"))
        segments = timer.data.get("segments", []) if timer else []
        if not segments:
            return ("outside", None) if membership == "outside" else ("ambiguous", None)
        observed, allocated, intervals = 0.0, 0, []
        for segment in segments:
            start, end = instant(segment["starts_at"]), instant(segment["ends_at"])
            duration = segment["seconds"]
            wall = (end - start).total_seconds()
            if wall < 0 or duration < 0 or not math.isfinite(duration):
                raise ValueError("invalid segment")
            if intervals and start < intervals[-1][1]:
                raise ValueError("overlapping or unordered segments")
            intervals.append((start, end))
            previous = observed
            observed += duration
            fraction = overlap(start, end, lower, upper)
            if fraction == 0:
                continue
            if start >= lower and end <= upper:
                allocation_start, allocation_end = previous, observed
            elif abs(wall - duration) < 2 and wall > 0:
                allocation_start = (
                    previous + max(0, (lower - start).total_seconds()) * duration / wall
                )
                allocation_end = (
                    previous
                    + min(wall, (upper - start).total_seconds()) * duration / wall
                )
            else:
                raise ValueError("clock movement makes boundary allocation unknown")
            allocated += math.floor(allocation_end + 1e-6) - math.floor(
                allocation_start + 1e-6
            )
        if math.floor(observed + 1e-6) != seconds:
            raise ValueError("segments do not explain fact")
        if observed == 0 and membership == "inside":
            return "inside", 0
        if not any(overlap(a, b, lower, upper) for a, b in intervals):
            return "outside", None
        # Floor cumulative elapsed positions so adjacent weeks sum to the saved fact.
        return "inside", allocated
    except (KeyError, ValueError, TypeError, OverflowError):
        return "ambiguous", None


def review_identity(owner, week, zone):
    return str(uuid5(NAMESPACE_URL, f"weekly-review:{owner}:{week}:{zone}"))


def review_view(resource, week, zone):
    return (
        store.view(resource)
        if resource
        else {
            "id": None,
            "kind": "weekly_review",
            "revision": 0,
            "data": {
                "week_start": week.isoformat(),
                "timezone": zone,
                "status": "awaiting_choice",
                "reason": None,
                "history": [],
            },
        }
    )


async def read_weekly_review(db, owner, week_start, report_timezone=None):
    settings = await store.rows(db, owner, "settings")
    cfg = settings[0] if settings else None
    timezone_name = report_timezone or (
        cfg.data.get("timezone") if cfg else "Asia/Shanghai"
    )
    try:
        validate_week(week_start, timezone_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    zone = ZoneInfo(timezone_name)
    lower, upper = bounds(week_start, zone)
    snapshots = await store.rows(db, owner, "plan_snapshot")
    blocks = await store.rows(db, owner, "plan_block")
    plans = {
        "original": plan_projection(snapshots, week_start, zone),
        "adjusted": plan_projection(snapshots, week_start, zone, latest=True),
        "current": current_projection(blocks, lower, upper),
    }
    gaps = set(g for p in plans.values() for g in p["gaps"])
    if plans["original"]["status"] != "complete":
        gaps.add("incomplete_original_baseline")
    all_records = effective(await store.rows(db, owner, "execution"))
    timers = {r.id: r for r in await store.rows(db, owner, "execution_timer")}
    tasks = {r.id: r for r in await store.rows(db, owner, "task")}
    records, ambiguous, unconfirmed, covered, complete_tasks = [], [], [], set(), set()
    ambiguous_completion = []
    for record in all_records:
        membership, seconds = record_seconds(record, timers, lower, upper)
        if membership == "outside":
            continue
        d = record.data
        if membership == "ambiguous":
            ambiguous.append(record.id)
        else:
            covered.update(covered_blocks(record))
        completion_membership = manual_membership(d, lower, upper)
        if d.get("source") == "timer":
            timer = timers.get(d.get("timer_id"))
            segments = timer.data.get("segments", []) if timer else []
            try:
                completion_membership = (
                    "inside"
                    if segments
                    and all(
                        lower
                        <= instant(segment["starts_at"])
                        <= instant(segment["ends_at"])
                        < upper
                        for segment in segments
                    )
                    and not d.get("unconfirmed_interval")
                    else "ambiguous"
                )
            except (KeyError, ValueError, TypeError):
                completion_membership = "ambiguous"
        if d.get("task_status") == "completed":
            if completion_membership == "inside":
                complete_tasks.add(d["task_id"])
            else:
                ambiguous_completion.append(record.id)
        if d.get("unconfirmed_interval"):
            unconfirmed.append(record.id)
        records.append(
            {
                "record_id": record.id,
                "execution_id": d.get("execution_id"),
                "task_id": d.get("task_id"),
                "task_title": tasks[d["task_id"]].data.get("title", "任务")
                if d.get("task_id") in tasks
                else "任务（当前不可用）",
                "plan_block_ids": sorted(covered_blocks(record)),
                "step_id": d.get("step_id"),
                "source": d.get("source", "manual"),
                "performed_on": d.get("performed_on"),
                "timezone": d.get("timezone"),
                "observed_seconds": seconds,
                "actual_seconds": seconds
                if not d.get("unconfirmed_interval")
                else None,
                "feedback": d.get("feedback"),
                "unfinished_reason": d.get("unfinished_reason"),
                "reason_prompt": "这次安排遇到了什么？可以补充中断、时间或安排方面的原因。"
                if d.get("feedback") != "completed" and not d.get("unfinished_reason")
                else None,
                "supersedes_id": d.get("supersedes_id"),
                "timer_id": d.get("timer_id"),
                "allocation_status": membership,
                "completion_allocation_status": completion_membership,
            }
        )
    plan_ids = {b["plan_block_id"] for p in plans.values() for b in p["blocks"]}
    missing = sorted(plan_ids - covered)
    if missing:
        gaps.add("missing_execution")
    if ambiguous:
        gaps.add("ambiguous_execution_week")
    if unconfirmed:
        gaps.add("unconfirmed_execution_interval")
    if ambiguous_completion:
        gaps.add("ambiguous_completion_week")
    known = [
        r["observed_seconds"] for r in records if r["observed_seconds"] is not None
    ]
    observed = sum(known) if known else None
    actual = observed if records and not (missing or ambiguous or unconfirmed) else None
    # Legacy allocations remain estimates; active actual coverage replaces them globally.
    actual_covered = (
        set().union(*(covered_blocks(r) for r in all_records)) if all_records else set()
    )
    estimates, unallocated = [], []
    states = {
        r.data.get("step_id"): r
        for r in await store.rows(db, owner, "execution_baseline")
    }
    for step in await store.rows(db, owner, "step"):
        state = states.get(step.id)
        allocations = (
            state.data.get("allocations", {})
            if state
            else {
                x["plan_block_id"]: x["minutes"]
                for x in legacy_estimates(step, blocks)
                if x["plan_block_id"]
            }
        )
        for bid, minutes in allocations.items():
            if bid in plan_ids and bid not in actual_covered:
                entry = {
                    "plan_block_id": bid,
                    "step_id": step.id,
                    "minutes": minutes,
                    "source": "legacy_estimate",
                    "baseline_id": state.id if state else None,
                }
                related = [b.data for b in blocks if b.id == bid]
                related += [
                    b
                    for s in snapshots
                    for b in s.data.get("approved_plan", {}).get("blocks", [])
                    if b.get("id") == bid
                ]
                try:
                    full = bool(related) and all(
                        instant(b["starts_at"]) >= lower
                        and instant(b["ends_at"]) <= upper
                        for b in related
                    )
                except (KeyError, TypeError, ValueError):
                    full = False
                if full:
                    estimates.append(entry)
                else:
                    unallocated.append({**entry, "week_attribution": "unknown"})
        remainder = (
            state.data.get("unallocated_minutes", 0)
            if state
            else max(0, step.data.get("spent_minutes", 0) - sum(allocations.values()))
        )
        if remainder and (
            not state or state.data.get("unallocated_resolution") != "replace"
        ):
            unallocated.append(
                {
                    "step_id": step.id,
                    "minutes": remainder,
                    "baseline_id": state.id if state else None,
                    "week_attribution": "unknown",
                }
            )
    dated_completions = {
        r.data.get("task_id")
        for r in all_records
        if r.data.get("task_status") == "completed"
    }
    undated_completed = sorted(
        t.id
        for t in tasks.values()
        if t.data.get("status") == "completed" and t.id not in dated_completions
    )
    if undated_completed:
        gaps.add("undated_task_completion")
    review = await db.get(Resource, review_identity(owner, week_start, timezone_name))
    return {
        "week_start": week_start,
        "week_end": week_start + timedelta(days=7),
        "timezone": timezone_name,
        "starts_at": lower.isoformat(),
        "ends_at": upper.isoformat(),
        "source_revision": cfg.revision if cfg else 0,
        "plans": plans,
        "execution": {
            "actual_seconds": actual,
            "observed_seconds": observed,
            "actual_minutes": actual / 60 if actual is not None else None,
            "effective_record_ids": [r["record_id"] for r in records],
            "missing_plan_block_ids": missing,
            "ambiguous_record_ids": ambiguous,
            "unconfirmed_execution_ids": unconfirmed,
            "completed_task_ids": sorted(complete_tasks),
            "ambiguous_completion_record_ids": ambiguous_completion,
            "undated_completed_task_ids": undated_completed,
            "completed_feedback_record_ids": [
                r["record_id"]
                for r in records
                if r["feedback"] == "completed"
                and r["completion_allocation_status"] == "inside"
            ],
            "records": records,
        },
        "estimates": {
            "allocated_minutes": sum(r["minutes"] for r in estimates),
            "allocations": estimates,
            "unallocated": unallocated,
        },
        "gaps": sorted(gaps),
        "review": review_view(review, week_start, timezone_name),
        "next_week_plan": await linked_plan_view(db, owner, review, week_start, timezone_name, cfg.revision if cfg else 0),
    }


async def save_review_action(db, owner, body):
    settings = await store.rows(db, owner, "settings")
    source_revision = settings[0].revision if settings else 0
    if source_revision != body.source_revision:
        raise HTTPException(409, "资料已变化，请刷新周复盘后再保存")
    rid = review_identity(owner, body.week_start, body.timezone)
    review = await db.get(Resource, rid)
    if (review.revision if review else 0) != body.revision:
        raise HTTPException(409, "复盘已更新，请刷新后再保存")
    history = review.data.get("history", []) if review else []
    status = {
        "accept": "accepted_pending_integration",
        "reject": "rejected",
        "restore": "awaiting_choice",
        "reason": review.data["status"] if review else "awaiting_choice",
    }[body.action]
    data = {
        "schema_version": 1,
        "week_start": body.week_start.isoformat(),
        "timezone": body.timezone,
        "status": status,
        "reason": body.reason.strip() if body.reason else None,
        "source_revision": body.source_revision,
        "accepted_intent_revision": (review.revision + 1 if review else 1) if body.action == "accept" else (review.data.get("accepted_intent_revision") if review else None),
        "plan_links": list(review.data.get("plan_links", [])) if review else [],
        "history": [
            *history,
            {
                "action": body.action,
                "reason": body.reason.strip() if body.reason else None,
                "recorded_at": now().isoformat(),
                "source_revision": body.source_revision,
            },
        ],
    }
    if review:
        review.data = data
        review.revision += 1
    else:
        review = Resource(id=rid, owner_id=owner, kind="weekly_review", data=data)
        db.add(review)
    await db.flush()
    await store.bump(db, owner)
    await record_change(
        db,
        owner,
        "weekly_review_changed",
        review.id,
        review.revision,
        {
            "week_start": body.week_start.isoformat(),
            "timezone": body.timezone,
            "action": body.action,
            "status": status,
            "source_revision": (await store.settings(db, owner)).revision,
            "formal_plan_changed": False,
        },
    )
    return store.view(review)


async def linked_plan_view(db, owner, review, week_start, timezone_name, source_revision):
    """Derive state without mutating snapshots, review history or confirmed plans."""
    from app.planning_history import PLANNER_RULE_VERSION

    target = week_start + timedelta(days=7)
    links = review.data.get("plan_links", []) if review else []
    result = {
        "week_start": target.isoformat(),
        "week_end": (target + timedelta(days=7)).isoformat(),
        "timezone": timezone_name,
        "status": "not_created",
        "draft_id": None,
        "draft": None,
        "snapshot_ids": [],
        "reason": None,
        "is_current_intent": False,
    }
    if not links:
        return result
    link = links[-1]
    result["is_current_intent"] = link.get("intent_revision") == review.data.get("accepted_intent_revision")
    draft = await db.get(Resource, link["draft_id"])
    if draft and (draft.owner_id != owner or draft.kind != "draft"):
        draft = None
    snapshots = [r.id for r in await store.rows(db, owner, "plan_snapshot") if r.data.get("draft_id") == link["draft_id"]]
    result.update({"draft_id": link["draft_id"], "generated_source_revision": link["source_revision"], "snapshot_ids": snapshots})
    # Approval evidence remains valid even when later facts have changed.
    if snapshots:
        result["status"] = "confirmed"
        return result
    reason = None
    if not draft:
        reason = "draft_unavailable"
    elif draft.data.get("status") != "pending":
        reason = "draft_" + draft.data.get("status", "unavailable")
    elif draft.data.get("source_revision") != source_revision:
        reason = "source_changed"
    elif draft.data.get("payload", {}).get("rule_version") != PLANNER_RULE_VERSION:
        reason = "rule_changed"
    elif store.digest(draft.data["payload"]) != draft.data.get("source", {}).get("generated_hash"):
        reason = "draft_changed"
    elif datetime.combine(target, time.min, ZoneInfo(timezone_name)) <= now():
        reason = "planning_week_started"
    result.update({"status": "invalidated" if reason else "pending", "reason": reason, "draft": store.view(draft) if draft and not reason else None})
    return result


async def create_next_week_draft(db, owner, body):
    """Consume an accepted intent; only original PlanReview can approve the result.

    The free-text reason is provenance, not a new scheduling rule. A's planner
    computes from confirmed facts and retains its version/hash confirmation guard.
    """
    from app.planner import generate_plan

    settings = await store.rows(db, owner, "settings")
    cfg = settings[0] if settings else None
    if not cfg or cfg.revision != body.source_revision:
        raise HTTPException(409, "资料已变化，请刷新周复盘后再生成")
    if cfg.data["timezone"] != body.timezone:
        raise HTTPException(409, "复盘时区与排程设置不同，请先核对设置时区")
    rid = review_identity(owner, body.week_start, body.timezone)
    review = await db.get(Resource, rid)
    if not review or review.owner_id != owner or review.kind != "weekly_review":
        raise HTTPException(409, "请先接受这项复盘调整意向")
    store.revision(review, body.revision)
    if review.data["status"] != "accepted_pending_integration" or not review.data.get("reason"):
        raise HTTPException(409, "请先接受这项复盘调整意向")
    target = body.week_start + timedelta(days=7)
    if datetime.combine(target, time.min, ZoneInfo(body.timezone)) <= now():
        raise HTTPException(422, "复盘对应的下周已经开始，请选择下一完整周")
    linked = await linked_plan_view(db, owner, review, body.week_start, body.timezone, cfg.revision)
    if linked["status"] == "pending" and linked["is_current_intent"]:
        return {"review": store.view(review), "draft": linked["draft"], "next_week_plan": linked}
    if linked["status"] == "confirmed" and linked["is_current_intent"]:
        raise HTTPException(409, "这项意向的下周计划已经确认，请重新核对并接受新的调整意向")
    draft = await generate_plan(db, owner, target=target, horizon=7)
    resource = await store.owned(db, owner, draft["id"], "draft")
    resource.data = {**resource.data, "source": {**resource.data["source"], "weekly_review_id": review.id, "weekly_review_revision": review.revision, "weekly_review_reason": review.data["reason"]}}
    link = {"draft_id": resource.id, "week_start": target.isoformat(), "timezone": body.timezone, "source_revision": cfg.revision, "accepted_review_revision": review.revision, "intent_revision": review.data.get("accepted_intent_revision"), "generated_at": now().isoformat()}
    review.data = {**review.data, "plan_links": [*review.data.get("plan_links", []), link]}
    review.revision += 1
    await db.flush()
    # Linking changes no scheduling fact. Bumping settings here would make A's
    # just-generated draft stale before the user could review it.
    await record_change(db, owner, "weekly_review_plan_linked", review.id, review.revision, {"draft_id": resource.id, "week_start": target.isoformat(), "formal_plan_changed": False})
    linked = await linked_plan_view(db, owner, review, body.week_start, body.timezone, cfg.revision)
    return {"review": store.view(review), "draft": store.view(resource), "next_week_plan": linked}
