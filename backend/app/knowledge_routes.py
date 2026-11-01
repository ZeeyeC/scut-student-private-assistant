from fastapi import APIRouter, Depends, Header, UploadFile, Form, Request
from app import knowledge, store
from app.knowledge_contracts import (
    KnowledgeDelete,
    KnowledgeWebCreate,
    KnowledgeSearchRequest,
    MAX_FILE_BYTES,
)


def knowledge_router(config, get_db, current_user):
    router = APIRouter(prefix="/api/knowledge")

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
            db, str(user.id), body.query, body.source_ids, body.course_id, body.limit
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
