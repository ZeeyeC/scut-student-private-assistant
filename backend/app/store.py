import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.contracts import StudentSettings
from app.db import Receipt, Resource


def view(r):
    return {"id": r.id, "kind": r.kind, "revision": r.revision, "data": r.data}


def digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


async def owned(db, owner, rid, kind=None):
    r = await db.get(Resource, rid)
    if not r or r.owner_id != owner or (kind and r.kind != kind):
        raise HTTPException(404, "资源不存在")
    return r


async def rows(db, owner, kind):
    return list(
        (
            await db.scalars(
                select(Resource)
                .where(Resource.owner_id == owner, Resource.kind == kind)
                .order_by(Resource.created_at, Resource.id)
            )
        ).all()
    )


async def settings(db, owner):
    result = await rows(db, owner, "settings")
    if result:
        return result[0]
    r = Resource(
        id=str(uuid4()),
        owner_id=owner,
        kind="settings",
        data=StudentSettings().model_dump(mode="json"),
    )
    db.add(r)
    await db.flush()
    return r


def revision(r, expected):
    if r.revision != expected:
        raise HTTPException(409, "数据已在另一端更新，请刷新后重新校对")


async def bump(db, owner):
    s = await settings(db, owner)
    s.revision += 1


async def replay(db, owner, scope, key, payload):
    if not key or len(key) > 160:
        raise HTTPException(422, "需要有效 Idempotency-Key")
    h = digest(payload)
    receipt = await db.scalar(
        select(Receipt).where(
            Receipt.owner_id == owner, Receipt.scope == scope, Receipt.key == key
        )
    )
    if receipt:
        if receipt.payload_hash != h:
            raise HTTPException(409, "幂等键已用于不同请求")
        return receipt
    return None


async def mutate(db, owner, scope, key, payload, operation):
    receipt = await replay(db, owner, scope, key, payload)
    if receipt:
        return receipt.result
    result = await operation()
    db.add(
        Receipt(
            owner_id=owner,
            scope=scope,
            key=key,
            payload_hash=digest(payload),
            result=result,
        )
    )
    await db.flush()
    return result
