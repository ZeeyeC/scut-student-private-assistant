"""Durable facts for later replanning; no background worker or model calls here."""

from uuid import NAMESPACE_URL, uuid5

from app.db import Resource, now

PLANNER_RULE_VERSION = "personal-facts-1"


async def record_change(db, owner, event_type, source_id, source_revision, details):
    identity = f"{owner}:{event_type}:{source_id}:{source_revision}"
    rid = str(uuid5(NAMESPACE_URL, "planning-event:" + identity))
    existing = await db.get(Resource, rid)
    if existing:
        return existing.id
    db.add(
        Resource(
            id=rid,
            owner_id=owner,
            kind="planning_event",
            data={
                "schema_version": 1,
                "event_type": event_type,
                "source_id": source_id,
                "source_revision": source_revision,
                "dedupe_key": identity,
                "occurred_at": now().isoformat(),
                # A later milestone may consume these. Nothing is auto-applied.
                "status": "recorded",
                "details": details,
            },
        )
    )
    await db.flush()
    return rid


async def save_snapshot(db, owner, draft, payload, previous):
    rid = str(uuid5(NAMESPACE_URL, f"planning-snapshot:{owner}:{draft.id}"))
    if not await db.get(Resource, rid):
        db.add(
            Resource(
                id=rid,
                owner_id=owner,
                kind="plan_snapshot",
                data={
                    "schema_version": 1,
                    "draft_id": draft.id,
                    "approved_at": now().isoformat(),
                    "rule_version": payload.get("rule_version", "demo2.2"),
                    "source_revision": draft.data["source_revision"],
                    "inputs": draft.data["source"].get("planning_inputs"),
                    "previous_blocks": previous,
                    "approved_plan": payload,
                },
            )
        )
        await db.flush()
    await record_change(
        db,
        owner,
        "plan_confirmed",
        draft.id,
        draft.revision,
        {
            "snapshot_id": rid,
            "target_date": payload["target_date"],
            "horizon_days": payload["horizon_days"],
        },
    )
    return rid
