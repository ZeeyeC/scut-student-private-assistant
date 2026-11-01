"""Recheck canonical facts after off-thread semantic scoring."""

from app import memories, store
from app.db_sessions import sqlite_transaction
from app.integrations_routes import semantic_enabled


async def recall_preferences(app, owner, query=""):
    async with sqlite_transaction(app.state.sessions) as db:
        baseline = await memories.recall(db, owner, query)
        enabled = await semantic_enabled(db, owner)
        generation = app.state.semantic_index.generation(owner)
        records = (
            [
                store.view(r)
                for r in await store.rows(db, owner, "assistant_memory")
                if r.data["status"] == "active"
            ]
            if enabled and baseline["enabled"]
            else []
        )
    scores = {}
    if records and query.strip():
        scores = await app.state.semantic_index.rank(
            owner, query, records, baseline["epoch"], generation=generation
        )
    async with sqlite_transaction(app.state.sessions) as db:
        result = await memories.recall(db, owner, query, semantic_scores=scores)
        if result["epoch"] != baseline["epoch"]:
            result = await memories.recall(db, owner, query)
            scores = {}
        result["retrieval_mode"] = "semantic+keyword" if scores else "keyword"
        return result
