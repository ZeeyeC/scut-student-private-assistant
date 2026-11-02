from fastapi import APIRouter, Depends, Header, UploadFile, Form, Request, Query
from typing import Literal
from app import knowledge, store
from app.knowledge_contracts import (
    KnowledgeDelete,
    KnowledgeWebCreate,
    KnowledgeSearchRequest,
    MAX_FILE_BYTES,
    KnowledgeClassification,
)


def knowledge_router(config, get_db, current_user):
    router = APIRouter(prefix="/api/knowledge")

    @router.get("/library")
    async def library(
        course_id: str | None = Query(None, max_length=100),
        unclassified: bool = False,
        query: str = Query("", max_length=255),
        sort: Literal["newest", "name"] = "newest",
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        user=Depends(current_user), db=Depends(get_db),
    ):
        from app.knowledge_library import inventory
        return await inventory(db, str(user.id), config, course_id=course_id,
                               unclassified=unclassified, query=query, sort=sort,
                               offset=offset, limit=limit)

    @router.patch("/sources/{rid}/course")
    async def classify(
        rid: str, body: KnowledgeClassification,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user), db=Depends(get_db),
    ):
        from app.knowledge_library import classify
        return await classify(db, str(user.id), rid, body, key)

    @router.get("/sources")
    async def sources(user=Depends(current_user), db=Depends(get_db)):
        return [
            store.view(r)
            for r in await store.rows(db, str(user.id), "knowledge_source")
        ]

    @router.get("/sources/{rid}")
    async def source(rid: str, user=Depends(current_user), db=Depends(get_db)):
        return store.view(await store.owned(db, str(user.id), rid, "knowledge_source"))

    @router.post("/documents")
    async def upload(
        file: UploadFile,
        course_id: str | None = Form(None),
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        raw = await file.read(MAX_FILE_BYTES + 1)
        return await knowledge.create_document(
            db, str(user.id), config, file.filename, raw, course_id or None, key
        )

    @router.post("/web")
    async def web(
        body: KnowledgeWebCreate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await knowledge.create_web(db, str(user.id), body, key)

    @router.post("/search")
    async def search(
        body: KnowledgeSearchRequest, user=Depends(current_user), db=Depends(get_db)
    ):
        return await knowledge.search_sources(
            db, str(user.id), body.query, body.source_ids, body.course_id, body.limit, unclassified=body.unclassified
        )

    @router.delete("/sources/{rid}")
    async def delete(
        rid: str,
        body: KnowledgeDelete,
        request: Request,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return await store.mutate(
            db,
            str(user.id),
            "knowledge-delete:" + rid,
            key,
            body.model_dump(),
            lambda: knowledge.delete_source(
                db,
                str(user.id),
                config,
                rid,
                body.revision,
                getattr(request.app.state, "semantic_index", None),
            ),
        )

    return router
