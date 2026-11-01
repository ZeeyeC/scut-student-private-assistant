"""Explicit per-owner connector configuration; no credential-bearing responses."""

import asyncio
from uuid import NAMESPACE_URL, uuid5
from fastapi import APIRouter, Depends, Header, Request
from pydantic import Field
from app import memories, store
from app.contracts import StrictModel
from app.db import Resource
from app.web_research import validate_search_endpoint


class SemanticWrite(StrictModel):
    enabled: bool


class SearchWrite(StrictModel):
    endpoint: str = Field(default="", max_length=2048)


class Empty(StrictModel):
    pass


async def preferences(db, owner, create=False):
    ident = str(uuid5(NAMESPACE_URL, "assistant-integrations:" + owner))
    r = await db.get(Resource, ident)
    if r is None and create:
        r = Resource(
            id=ident,
            owner_id=owner,
            kind="integration_settings",
            data={"semantic_enabled": False, "search_endpoint": None},
        )
        db.add(r)
        await db.flush()
    return r


async def search_endpoint(db, owner, config):
    r = await preferences(db, owner)
    return (
        r.data.get("search_endpoint")
        if r and r.data.get("search_endpoint") is not None
        else config.search_endpoint
    )


async def semantic_enabled(db, owner):
    r = await preferences(db, owner)
    return bool(r and r.data.get("semantic_enabled"))


def integrations_router(config, get_db, current_user):
    router = APIRouter(prefix="/api/integrations")

    @router.get("")
    async def status(request: Request, user=Depends(current_user), db=Depends(get_db)):
        owner = str(user.id)
        endpoint = await search_endpoint(db, owner, config)
        return {
            "semantic": {
                **await request.app.state.semantic_index.status(),
                "enabled": await semantic_enabled(db, owner),
            },
            "search": {"configured": bool(endpoint), "endpoint": endpoint},
        }

    @router.put("/semantic")
    async def semantic(
        body: SemanticWrite,
        request: Request,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)

        async def op():
            await memories.idle(db, owner)
            r = await preferences(db, owner, True)
            r.data = {**r.data, "semantic_enabled": body.enabled}
            r.revision += 1
            await memories.epoch(db, owner)
            return {"enabled": body.enabled}

        return await store.mutate(
            db, owner, "semantic-settings", key, body.model_dump(), op
        )

    @router.post("/semantic/prepare")
    async def prepare(
        body: Empty,
        request: Request,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        index = request.app.state.semantic_index

        async def op():
            if (
                not getattr(request.app.state, "semantic_prepare_task", None)
                or request.app.state.semantic_prepare_task.done()
            ):
                task = asyncio.create_task(index.prepare())
                request.app.state.semantic_prepare_task = task
                request.app.state.running_tasks.add(task)
                task.add_done_callback(request.app.state.running_tasks.discard)
            return {"status": "preparing"}

        return await store.mutate(db, str(user.id), "semantic-prepare", key, {}, op)

    @router.post("/search/test")
    async def test_search(
        body: SearchWrite, user=Depends(current_user), db=Depends(get_db)
    ):
        from app.web_research import search_web

        endpoint = validate_search_endpoint(body.endpoint)
        await db.commit()
        result = await search_web("连接测试", endpoint)
        return {"connected": True, "provider": result["provider"]}

    @router.put("/search")
    async def search(
        body: SearchWrite,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        endpoint = validate_search_endpoint(body.endpoint)

        async def op():
            r = await preferences(db, str(user.id), True)
            r.data = {**r.data, "search_endpoint": endpoint}
            r.revision += 1
            return {"configured": bool(endpoint), "endpoint": endpoint}

        return await store.mutate(
            db, str(user.id), "search-settings", key, body.model_dump(), op
        )

    return router
