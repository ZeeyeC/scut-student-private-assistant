"""Cancellation must finish SQLite cleanup before a request/worker exits."""

import asyncio
from contextlib import asynccontextmanager

import anyio
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.agent import agent_router, transaction
from app.main import create_app


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def isolated_app(tmp_path):
    app = create_app(
        {
            "app_mode": "shared",
            "settings_file": str(tmp_path / "model.env"),
            "database_url": f"sqlite+aiosqlite:///{tmp_path}/test.db",
            "upload_dir": str(tmp_path / "uploads"),
            "agent_db_path": str(tmp_path / "agent.db"),
            "model_api_key": "",
            "text_model": "",
            "vision_model": "",
        }
    )
    engine = app.state.sessions.kw["bind"]
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE cancellation_probe (value TEXT)"))
    yield app
    await app.state.gateway.aclose()
    await engine.dispose()


@pytest.mark.parametrize("boundary", ["request", "agent"])
async def test_cancelled_transaction_rolls_back_before_returning_connection(
    isolated_app, boundary
):
    # Removing cancellation-safe cleanup must leave a checked-out connection,
    # even though the original cancellation still propagates out of the context.
    app = isolated_app
    context = (
        asynccontextmanager(app.state.get_db)
        if boundary == "request"
        else lambda: transaction(app)
    )
    cancelled = False
    with anyio.CancelScope() as scope:
        try:
            async with context() as db:
                await db.execute(
                    text("INSERT INTO cancellation_probe VALUES ('partial')")
                )
                scope.cancel()
                await anyio.sleep(0)
        except asyncio.CancelledError:
            cancelled = True
            raise
    assert cancelled, "transaction cleanup must not consume request cancellation"
    engine = app.state.sessions.kw["bind"]
    assert engine.pool.checkedout() == 0, (
        "request returned before SQLite cleanup finished"
    )
    async with app.state.sessions() as db:
        assert await db.scalar(text("SELECT count(*) FROM cancellation_probe")) == 0
        await db.execute(text("BEGIN IMMEDIATE"))
        await db.execute(text("INSERT INTO cancellation_probe VALUES ('next request')"))
        await db.commit()
    async with app.state.sessions() as db:
        assert (
            await db.scalar(text("SELECT value FROM cancellation_probe"))
            == "next request"
        )


async def test_sse_disconnect_during_read_releases_sqlite_before_refresh(isolated_app):
    from types import SimpleNamespace

    import httpx
    from sqlalchemy import event
    from sqlalchemy.util import await_only

    from app.db import Base, Resource

    app = isolated_app
    engine = app.state.sessions.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with app.state.sessions() as db:
        db.add(
            Resource(
                id="run", owner_id="alice", kind="agent_run", data={"status": "running"}
            )
        )
        await db.commit()
    app.dependency_overrides[app.state.current_user] = lambda: SimpleNamespace(
        id="alice"
    )
    reading = asyncio.Event()
    messages = []

    async def pause_for_disconnect():
        reading.set()
        await anyio.sleep(0)
        await anyio.sleep(0)

    def before_rollback(connection):
        # A real SQLite read transaction is ending; make the disconnect land
        # during that I/O boundary rather than depending on wall-clock sleeps.
        await_only(pause_for_disconnect())

    event.listen(engine.sync_engine, "rollback", before_rollback)

    async def receive():
        await reading.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    try:
        with anyio.fail_after(5):
            await app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.3"},
                    "http_version": "1.1",
                    "method": "GET",
                    "scheme": "http",
                    "path": "/api/agent/runs/run/events",
                    "raw_path": b"/api/agent/runs/run/events",
                    "query_string": b"",
                    "root_path": "",
                    "headers": [],
                    "server": ("testserver", 80),
                    "client": ("127.0.0.1", 12345),
                },
                receive,
                send,
            )
        assert reading.is_set()
        assert messages[0]["status"] == 200
        assert engine.pool.checkedout() == 0, (
            "SSE disconnected before its read session closed"
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            refreshed = await client.get("/api/agent/runs/run")
            assert refreshed.status_code == 200
            assert refreshed.json()["data"]["status"] == "running"
        async with app.state.sessions() as db:
            assert (await db.get(Resource, "run")).data["status"] == "running"
            await db.execute(text("BEGIN IMMEDIATE"))
            await db.commit()
    finally:
        event.remove(engine.sync_engine, "rollback", before_rollback)


@pytest.mark.parametrize("cancellation", ["anyio", "shutdown"])
async def test_sse_cancellation_at_read_cleanup_does_not_detach_close(
    isolated_app, cancellation
):
    from types import SimpleNamespace

    from sqlalchemy import event
    from starlette.requests import Request

    from app.db import Base, Resource

    app = isolated_app
    engine = app.state.sessions.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with app.state.sessions() as db:
        db.add(
            Resource(
                id="run", owner_id="alice", kind="agent_run", data={"status": "running"}
            )
        )
        await db.commit()
    endpoint = next(
        route.endpoint
        for route in agent_router(app.state.get_db, app.state.current_user).routes
        if route.path == "/api/agent/runs/{rid}/events"
    )

    async def receive():
        await anyio.sleep_forever()

    request = Request({"type": "http", "app": app}, receive)
    async with app.state.sessions() as db:
        response = await endpoint(
            "run", request, 0, None, SimpleNamespace(id="alice"), db
        )
    cancelled = False
    with anyio.CancelScope() as scope:

        def disconnect(connection):
            if cancellation == "anyio":
                scope.cancel()
            else:
                asyncio.current_task().cancel()

        event.listen(engine.sync_engine, "rollback", disconnect)
        try:
            await anext(response.body_iterator)
        except asyncio.CancelledError:
            cancelled = True
        finally:
            event.remove(engine.sync_engine, "rollback", disconnect)
    assert cancelled
    assert engine.pool.checkedout() == 0, "SSE cleanup escaped into an unawaited task"


async def test_shutdown_waits_for_cancelled_worker_and_database_reopens(isolated_app):
    app = isolated_app
    started = asyncio.Event()

    async def worker():
        async with transaction(app) as db:
            await db.execute(
                text("INSERT INTO cancellation_probe VALUES ('unfinished worker')")
            )
            started.set()
            await anyio.sleep_forever()

    async with app.router.lifespan_context(app):
        task = asyncio.create_task(worker())
        app.state.running_tasks.add(task)
        await started.wait()
    assert task.cancelled()
    assert app.state.sessions.kw["bind"].pool.checkedout() == 0
    async with app.router.lifespan_context(app):
        async with transaction(app) as db:
            assert await db.scalar(text("SELECT count(*) FROM cancellation_probe")) == 0
            await db.execute(text("INSERT INTO cancellation_probe VALUES ('reopened')"))
