import time
from fastapi import APIRouter, Depends, Header, Request, HTTPException
from app import store, zotero_bridge as bridge
from app.contracts import StrictModel
from app.zotero_contracts import (
    ZoteroSettingsWrite,
    ZoteroSearch,
    ZoteroItem,
    ZoteroCollections,
)


class Empty(StrictModel):
    pass


def zotero_router(config, get_db, current_user):
    router = APIRouter(prefix="/api/zotero")

    @router.get("/status")
    async def status(request: Request, user=Depends(current_user), db=Depends(get_db)):
        owner = str(user.id)
        r = await bridge.settings(db, owner)
        result = bridge.view(
            r,
            bridge.read_token(
                config, owner, r.data if r else bridge.DEFAULTS, r.revision if r else 0
            ),
        )
        previous = getattr(request.app.state, "zotero_status", {}).get(owner)
        if (
            previous
            and previous["revision"] == result["revision"]
            and time.monotonic() - previous["at"] < 300
        ):
            result["connected"] = previous["connected"]
        return result

    @router.put("/settings")
    async def settings(
        body: ZoteroSettingsWrite,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        payload = body.model_dump(mode="json")
        old = None
        previous = await bridge.settings(db, owner)
        old_binding = bridge.secret_binding(
            previous.data if previous else bridge.DEFAULTS,
            previous.revision if previous else 0,
        )

        async def op():
            nonlocal old
            r, old, new = await bridge.save(db, owner, config, body)
            bridge.write_token(
                config, owner, new, binding=bridge.secret_binding(r.data, r.revision)
            )
            return bridge.view(r, new)

        try:
            result = await store.mutate(db, owner, "zotero-settings", key, payload, op)
            await db.commit()
            return result
        except BaseException:
            if old is not None:
                bridge.write_token(config, owner, old, binding=old_binding)
            raise

    @router.post("/test")
    async def test(
        body: Empty, request: Request, user=Depends(current_user), db=Depends(get_db)
    ):
        owner = str(user.id)
        r = await bridge.settings(db, owner)
        revision = r.revision if r else 0
        await db.commit()
        if not hasattr(request.app.state, "zotero_status"):
            request.app.state.zotero_status = {}
        try:
            result = await bridge.call(
                request.app, owner, "zotero_get_collections", {"limit": 1}, test=True
            )
        except HTTPException:
            request.app.state.zotero_status[owner] = {
                "revision": revision,
                "connected": False,
                "at": time.monotonic(),
            }
            raise
        if not hasattr(request.app.state, "zotero_status"):
            request.app.state.zotero_status = {}
        request.app.state.zotero_status[owner] = {
            "revision": revision,
            "connected": True,
            "at": time.monotonic(),
        }
        return {"connected": True, "tools": result["tools"], "read_only": True}

    @router.post("/search")
    async def search(
        body: ZoteroSearch,
        request: Request,
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        await db.commit()
        return await bridge.call(
            request.app,
            str(user.id),
            "zotero_search_items",
            {
                "query": body.query,
                "limit": body.limit,
                "collection_key": body.collection_key,
                "search_all_libraries": False,
            },
        )

    @router.post("/item")
    async def item(
        body: ZoteroItem,
        request: Request,
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        await db.commit()
        return await read_item(request.app, str(user.id), body.item_key, body.section)

    @router.post("/collections")
    async def collections(
        body: ZoteroCollections,
        request: Request,
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        await db.commit()
        return await bridge.call(
            request.app, str(user.id), "zotero_get_collections", {"limit": body.limit}
        )

    return router


async def read_item(app, owner, key, section):
    if section == "notes":
        result = await bridge.call(
            app,
            owner,
            "zotero_get_notes",
            {"item_key": key, "limit": 20, "truncate": True},
            extra=(
                "zotero_get_annotations",
                {"item_key": key, "limit": 20, "use_pdf_extraction": False},
            ),
        )
    else:
        tool = (
            "zotero_get_item_metadata"
            if section == "metadata"
            else "zotero_get_item_fulltext"
        )
        result = await bridge.call(app, owner, tool, {"item_key": key})
    return {**result, "item_key": key, "source": "zotero://select/library/items/" + key}
