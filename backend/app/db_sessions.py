"""SQLite session cleanup that stays owned by its cancelled request or worker."""

from contextlib import asynccontextmanager

import anyio
from sqlalchemy import text


@asynccontextmanager
async def session_scope(sessions):
    db = sessions()
    try:
        yield db
    finally:
        # AsyncSession.__aexit__ starts a separate close task and asyncio.shield
        # alone cannot await it inside AnyIO's repeatedly cancelled request scope.
        # Finish close here, before the owner returns or the engine is disposed.
        with anyio.CancelScope(shield=True):
            await db.close()


@asynccontextmanager
async def sqlite_transaction(sessions):
    async with session_scope(sessions) as db:
        try:
            await db.execute(text("BEGIN IMMEDIATE"))
            yield db
            await db.commit()
        except BaseException:
            # CancelledError and GeneratorExit also abandon a transaction. Only
            # cleanup is shielded: the original cancellation still propagates.
            with anyio.CancelScope(shield=True):
                await db.rollback()
            raise
