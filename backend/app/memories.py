"""Owner-scoped memory aggregate. Caller owns the serialized transaction."""

import re
import unicodedata
from datetime import datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException

from app import profiles, store
from app.db import Resource, now
from app.memory_contracts import MemoryProposal
from app.profile_contracts import ProfileInput, ProfileWrite

DEFAULTS = dict(recall_enabled=True, suggestions_enabled=False, privacy_epoch=0)
BUSY = {"queued", "running", "resume_queued", "waiting_approval"}
LABELS = {
    "focus_minutes": "专注时长",
    "break_minutes": "休息时长",
    "daily_load_minutes": "每日学习上限",
}


def identity(owner, key):
    return str(uuid5(NAMESPACE_URL, f"assistant-memory:{owner}:{key}"))


def normalize(key):
    return unicodedata.normalize("NFKC", key).strip().casefold()


async def settings(db, owner, create=False):
    r = await db.get(Resource, identity(owner, ":settings"))
    if r is None and create:
        r = Resource(
            id=identity(owner, ":settings"),
            owner_id=owner,
            kind="memory_settings",
            data=dict(DEFAULTS),
        )
        db.add(r)
        await db.flush()
    return r


async def epoch(db, owner):
    if db.info.get("semantic_index"):
        await db.info["semantic_index"].clear_owner(owner)
    r = await settings(db, owner, True)
    r.data = {**r.data, "privacy_epoch": r.data["privacy_epoch"] + 1}
    r.revision += 1


async def idle(db, owner):
    if any(
        r.data.get("status") in BUSY for r in await store.rows(db, owner, "agent_run")
    ):
        raise HTTPException(
            409, "助手正在运行或等待批准，请先结束或拒绝该操作再修改记忆"
        )


def meta(r):
    return {"id": r.id, "revision": r.revision, "status": r.data.get("status")}


def safe_text(body, secrets):
    text = body.key + " " + body.content
    patterns = [
        r"(?i)\bsk-[a-z0-9_-]{8,}",
        r"(?i)(api[_ -]?key|password|token|密钥|密码)\s*[:：=]\s*\S+",
        r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
        r"(?<!\d)1[3-9]\d{9}(?!\d)",
        r"(?<!\d)\d{17}[\dXx](?!\d)",
    ]
    if any(re.search(p, text) for p in patterns) or any(
        s and s in text for s in secrets
    ):
        raise HTTPException(422, "记忆不能包含凭据、联系方式或身份号码，请删除敏感信息")


async def source_checked(db, owner, source):
    result = {
        k: source[k] for k in ("kind", "run_id", "thread_id", "explicit") if k in source
    }
    if result.get("run_id"):
        run = await store.owned(db, owner, result["run_id"], "agent_run")
        if run.data["thread_id"] != result.get("thread_id"):
            raise HTTPException(409, "记忆来源会话不符")
    return result


async def reconcile(db, owner):
    profile = await profiles.read_profile(db, owner)
    changed = False
    for r in await store.rows(db, owner, "assistant_memory"):
        d = r.data
        if d["status"] != "active":
            continue
        status = None
        if d.get("expires_at") and datetime.fromisoformat(d["expires_at"]) <= now():
            status = "expired"
        elif (
            d.get("profile_field")
            and profile["data"]["preferences"].get(d["profile_field"])
            != d["profile_value"]
        ):
            status = "superseded"
        if status:
            r.data = {**d, "status": status}
            r.revision += 1
            changed = True
    if changed:
        await epoch(db, owner)


async def view(db, owner):
    await reconcile(db, owner)
    s = await settings(db, owner)
    return {
        "settings": store.view(s)
        if s
        else {"id": None, "revision": 0, "data": dict(DEFAULTS)},
        "memories": [
            store.view(r) for r in await store.rows(db, owner, "assistant_memory")
        ],
        "candidates": [
            store.view(r)
            for r in await store.rows(db, owner, "memory_candidate")
            if r.data["status"] == "pending"
        ],
    }


async def snapshot(db, owner, key, mapped=False):
    r = await db.get(Resource, identity(owner, key))
    return {
        "base_revision": r.revision if r else 0,
        "profile_revision": (await profiles.read_profile(db, owner))["revision"]
        if mapped
        else None,
    }


async def propose(db, owner, body: MemoryProposal, source, secret_values=()):
    safe_text(body, secret_values)
    source = await source_checked(db, owner, source)
    s = await settings(db, owner)
    if not source.get("explicit") and not (s and s.data["suggestions_enabled"]):
        raise HTTPException(422, "请明确要求记住偏好，或在设置中允许记忆建议")
    key = normalize(body.key)
    if key in LABELS and body.profile_field != key:
        raise HTTPException(422, "标准学习偏好请使用对应的同步字段")
    if key.startswith(":"):
        raise HTTPException(422, "记忆名称无效")
    memories = await store.rows(db, owner, "assistant_memory")
    if len(memories) >= 200 and not any(r.data["key"] == key for r in memories):
        raise HTTPException(422, "记忆已达到200条上限，请先整理")
    candidates = await store.rows(db, owner, "memory_candidate")
    if sum(r.data["status"] == "pending" for r in candidates) >= 30:
        raise HTTPException(422, "待确认记忆过多，请先校对")
    data = body.model_dump(mode="json")
    data["key"] = key
    if body.profile_field:
        data["content"] = f"{LABELS[body.profile_field]}：{body.profile_value} 分钟"
    data.update(
        action="upsert", status="pending", source=source, created_at=now().isoformat()
    )
    data.update(await snapshot(db, owner, key, bool(body.profile_field)))
    r = Resource(id=str(uuid4()), owner_id=owner, kind="memory_candidate", data=data)
    db.add(r)
    await db.flush()
    return meta(r)


async def propose_forget(db, owner, memory_id, revision, source):
    r = await store.owned(db, owner, memory_id, "assistant_memory")
    store.revision(r, revision)
    if r.data["status"] == "forgotten":
        raise HTTPException(409, "该记忆已遗忘")
    source = await source_checked(db, owner, source)
    if not source.get("explicit"):
        raise HTTPException(422, "请明确要求遗忘这项记忆")
    if (
        sum(
            c.data["status"] == "pending"
            for c in await store.rows(db, owner, "memory_candidate")
        )
        >= 30
    ):
        raise HTTPException(422, "请先校对待确认记忆")
    c = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="memory_candidate",
        data={
            **{
                k: r.data.get(k)
                for k in (
                    "key",
                    "content",
                    "category",
                    "profile_field",
                    "profile_value",
                )
            },
            "action": "forget",
            "status": "pending",
            "source": source,
            "created_at": now().isoformat(),
            **await snapshot(
                db, owner, r.data["key"], bool(r.data.get("profile_field"))
            ),
        },
    )
    db.add(c)
    await db.flush()
    return meta(c)


async def candidate(db, owner, cid, revision):
    r = await store.owned(db, owner, cid, "memory_candidate")
    store.revision(r, revision)
    if r.data["status"] != "pending":
        raise HTTPException(409, "候选已处理，请刷新")
    return r


async def refresh_candidate(db, owner, cid, revision):
    r = await candidate(db, owner, cid, revision)
    r.data = {
        **r.data,
        **await snapshot(db, owner, r.data["key"], bool(r.data.get("profile_field"))),
    }
    r.revision += 1
    return meta(r)


async def write_profile(db, owner, field, value):
    p = await profiles.read_profile(db, owner)
    data = {
        k: p["data"][k]
        for k in ("timezone", "effective_from", "effective_until", "preferences")
    }
    data["timezone"] = (
        data["timezone"] or (await store.settings(db, owner)).data["timezone"]
    )
    data["preferences"] = {**data["preferences"], field: value}
    await profiles.replace_profile(
        db,
        owner,
        ProfileWrite(revision=p["revision"], data=ProfileInput.model_validate(data)),
    )


async def wipe(db, owner, r):
    field = r.data.get("profile_field")
    if field:
        p = await profiles.read_profile(db, owner)
        if p["data"]["preferences"].get(field) == r.data["profile_value"]:
            await write_profile(db, owner, field, None)
    key = r.data["key"]
    r.data = {
        "key": key,
        "content": "",
        "category": r.data["category"],
        "status": "forgotten",
    }
    r.revision += 1
    for c in await store.rows(db, owner, "memory_candidate"):
        if c.data["key"] == key:
            c.data = {
                "key": key,
                "content": "",
                "action": c.data["action"],
                "status": "rejected",
            }
            c.revision += 1


async def confirm_candidate(db, owner, cid, revision):
    await idle(db, owner)
    await reconcile(db, owner)
    c = await candidate(db, owner, cid, revision)
    d = c.data
    latest = await snapshot(db, owner, d["key"], bool(d.get("profile_field")))
    if any(latest[k] != d.get(k) for k in latest):
        raise HTTPException(409, "记忆或偏好已变化，请重新校对后确认")
    r = await db.get(Resource, identity(owner, d["key"]))
    if d["action"] == "forget":
        if not r:
            raise HTTPException(409, "记忆已变化")
        await wipe(db, owner, r)
        await epoch(db, owner)
    else:
        # Replacing a mapped memory must not orphan its old canonical preference.
        if (
            r
            and r.data.get("profile_field")
            and r.data["profile_field"] != d.get("profile_field")
        ):
            p = await profiles.read_profile(db, owner)
            field = r.data["profile_field"]
            if p["data"]["preferences"].get(field) == r.data["profile_value"]:
                await write_profile(db, owner, field, None)
        if d.get("expires_at") and datetime.fromisoformat(d["expires_at"]) <= now():
            raise HTTPException(409, "候选有效期已过，请修改后重新提出")
        if d.get("profile_field"):
            await write_profile(db, owner, d["profile_field"], d["profile_value"])
        data = {
            k: d.get(k)
            for k in (
                "key",
                "content",
                "category",
                "expires_at",
                "profile_field",
                "profile_value",
                "source",
            )
        }
        data.update(status="active", confirmed_at=now().isoformat())
        if r:
            r.data = data
            r.revision += 1
            await epoch(db, owner)
        else:
            r = Resource(
                id=identity(owner, d["key"]),
                owner_id=owner,
                kind="assistant_memory",
                data=data,
            )
            db.add(r)
        c.data = {**d, "status": "confirmed"}
        c.revision += 1
    await db.flush()
    return meta(r)


async def reject_candidate(db, owner, cid, revision):
    c = await candidate(db, owner, cid, revision)
    c.data = {**c.data, "status": "rejected"}
    c.revision += 1
    return meta(c)


async def write_preferences(db, owner, body):
    await idle(db, owner)
    s = await settings(db, owner)
    if (s.revision if s else 0) != body.revision:
        raise HTTPException(409, "记忆设置已变化，请刷新")
    s = await settings(db, owner, True)
    changed = s.data["recall_enabled"] != body.recall_enabled
    if changed and db.info.get("semantic_index"):
        await db.info["semantic_index"].clear_owner(owner)
    s.data = {
        **s.data,
        "recall_enabled": body.recall_enabled,
        "suggestions_enabled": body.suggestions_enabled,
        "privacy_epoch": s.data["privacy_epoch"] + int(changed),
    }
    s.revision += 1
    return meta(s)


async def clear_memories(db, owner, revision):
    await idle(db, owner)
    s = await settings(db, owner)
    if (s.revision if s else 0) != revision:
        raise HTTPException(409, "记忆设置已变化，请刷新")
    for r in await store.rows(db, owner, "assistant_memory"):
        if r.data["status"] != "forgotten":
            await wipe(db, owner, r)
    for c in await store.rows(db, owner, "memory_candidate"):
        c.data = {
            "key": c.data["key"],
            "content": "",
            "action": c.data["action"],
            "status": "rejected",
        }
        c.revision += 1
    await epoch(db, owner)
    return {"cleared": True}


async def recall(db, owner, query="", limit=5, max_chars=1000, semantic_scores=None):
    await reconcile(db, owner)
    s = await settings(db, owner)
    result = {
        "enabled": s.data["recall_enabled"] if s else True,
        "epoch": s.data["privacy_epoch"] if s else 0,
        "items": [],
    }
    if not result["enabled"]:
        return result
    terms = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", query.casefold())[:200]
    all_query = not query or bool(
        re.search("记忆|记住|偏好|remember|preference", query, re.I)
    )
    scored = []
    for r in await store.rows(db, owner, "assistant_memory"):
        if r.data["status"] != "active":
            continue
        d = r.data
        score = sum(t in (d["key"] + d["content"]).casefold() for t in terms)
        semantic = (semantic_scores or {}).get(r.id)
        similarity = semantic.get("score", 0) if isinstance(semantic, dict) and semantic.get("revision") == r.revision else 0
        if score or all_query or d["category"] == "interaction_preference" or similarity >= 0.5:
            scored.append((score / max(1, len(terms)) + similarity * 2, r))
    budget = min(1000, max(0, max_chars))
    for _, r in sorted(scored, key=lambda x: (-x[0], x[1].id))[: min(5, max(0, limit))]:
        content = r.data["content"][:budget]
        if not content:
            break
        result["items"].append(
            {"id": r.id, "revision": r.revision, **r.data, "content": content}
        )
        budget -= len(content)
    return result


async def checkpoint_scope(db, owner, thread_id):
    await reconcile(db, owner)
    s = await settings(db, owner)
    e = s.data["privacy_epoch"] if s else 0
    return f"{thread_id}:memory:{e}" if e else thread_id
