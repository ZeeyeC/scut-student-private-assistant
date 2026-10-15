from fastapi import HTTPException

from app import store


async def delete_draft(db, owner, rid, expected):
    draft = await store.owned(db, owner, rid, "draft")
    store.revision(draft, expected)
    if draft.data["status"] != "pending":
        raise HTTPException(409, "只能删除尚未保存的草稿")
    browser_session = draft.data.get("source", {}).get("browser_session")
    if browser_session:
        session = await store.owned(db, owner, browser_session, "browser_import")
        if session.data["draft_id"] != rid or session.data["status"] == "completed":
            raise HTTPException(409, "导入状态已改变，请刷新后重新校对")
        session.data = {**session.data, "status": "cancelled"}
        session.revision += 1
    # Keep the tombstone so delayed confirmations cannot revive discarded drafts.
    draft.data = {**draft.data, "status": "deleted"}
    draft.revision += 1
    return {"deleted": True, "id": rid}


async def delete_task(db, owner, rid, expected):
    task = await store.owned(db, owner, rid, "task")
    store.revision(task, expected)
    steps = [s for s in await store.rows(db, owner, "step") if s.data["task_id"] == rid]
    step_ids = {s.id for s in steps}
    blocks = [
        b
        for b in await store.rows(db, owner, "plan_block")
        if b.data.get("task_id") == rid or b.data.get("step_id") in step_ids
    ]
    for resource in [*blocks, *steps, task]:
        await db.delete(resource)
    for draft in await store.rows(db, owner, "draft"):
        if draft.data["status"] != "pending":
            continue
        kind, payload = draft.data["draft_kind"], draft.data["payload"]
        # Every plan was computed from the full task set and must be regenerated.
        if kind == "plan" or (kind == "decomposition" and payload["task_id"] == rid):
            draft.data = {
                **draft.data,
                "status": "superseded",
                "invalidated_reason": "待办已删除，请重新生成",
            }
            draft.revision += 1
    await store.bump(db, owner)
    return {"deleted": True, "id": rid, "steps": len(steps), "plan_blocks": len(blocks)}
