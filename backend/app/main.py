import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import store
from app.after_class import after_class_router
from app.agent import agent_router, pending_approval
from app.assignments import assignment_router
from app.auth import UserCreate, UserRead, build_auth
from app.browser_imports import browser_router
from app.config import Config
from app.constraints import constraint_router
from app.contracts import SettingsUpdate
from app.course_changes import course_change_router
from app.data_routes import data_router
from app.db_sessions import sqlite_transaction
from app.desktop_import_bridge import desktop_import_router
from app.execution_routes import execution_router
from app.goal_routes import goal_router
from app.model_gateway import ModelGateway
from app.paths import resource_root
from app.pet_status import pet_router
from app.planner import planner_router
from app.processes import process_alive
from app.profile_routes import profile_router
from app.review_routes import review_router
from app.routes import business_router
from app.schedule_reminders import reminder_router
from app.tasks import task_router
from app.timer_routes import timer_router
from app.timetable_recognition import timetable_recognition_router


def create_app(config=None):
    config = Config(**(config or {})) if not isinstance(config, Config) else config
    config.prepare()
    engine = create_async_engine(config.database_url, connect_args={"timeout": 30})
    from app.semantic_index import SemanticIndex
    semantic_index = SemanticIndex(Path(config.agent_db_path).parent / "knowledge-index")
    sessions = async_sessionmaker(engine, expire_on_commit=False, info={"semantic_index": semantic_index, "data_generations": {}})

    @asynccontextmanager
    async def lifespan(app):
        lock = Path(config.database_url.split("///", 1)[1] + ".server.lock")
        if lock.exists():
            try:
                pid = int(lock.read_text())
                alive = process_alive(pid)
            except ValueError:
                alive = False
            if not alive:
                lock.unlink(missing_ok=True)
            else:
                raise RuntimeError("同一 SQLite 后端只允许一个服务进程")
        # Exclusive creation also closes the two-starting-process race.
        try:
            with lock.open("x") as file:
                file.write(str(os.getpid()))
        except FileExistsError as exc:
            raise RuntimeError("同一 SQLite 后端只允许一个服务进程") from exc

        def migrate():
            cfg = AlembicConfig(str(resource_root() / "backend" / "alembic.ini"))
            cfg.set_main_option(
                "script_location", str(resource_root() / "backend" / "migrations")
            )
            cfg.set_main_option(
                "sqlalchemy.url", config.database_url.replace("+aiosqlite", "")
            )
            command.upgrade(cfg, "head")

        try:
            await asyncio.to_thread(migrate)
            async with AsyncSqliteSaver.from_conn_string(
                config.agent_db_path
            ) as checkpointer:
                await checkpointer.setup()
                app.state.checkpointer = checkpointer
                app.state.running_tasks = set()
                # Never silently restart a model job or re-execute a tool after a crash.
                from sqlalchemy import select

                from app.db import Resource

                recoverable = []
                async with sessions() as db:
                    for r in await db.scalars(
                        select(Resource).where(Resource.kind.in_(["job", "agent_run"]))
                    ):
                        if r.data["status"] in ("queued", "running", "resume_queued"):
                            if r.kind == "agent_run":
                                recoverable.append(
                                    (r.owner_id, r.id, r.data.get("checkpoint_id", r.data["thread_id"]))
                                )
                            r.data = {
                                **r.data,
                                "status": "failed",
                                "error": "服务重启中断了处理，未自动重试。请检查草稿和历史后重试。",
                            }
                            r.revision += 1
                    await db.commit()
                # A checkpoint can commit its interrupt just before the business
                # approval transaction. Recover that gap without calling a model
                # or executing any tool; require a fresh human decision as needed.
                for owner, rid, thread_id in recoverable:
                    checkpoint = await checkpointer.aget_tuple(
                        {"configurable": {"thread_id": thread_id}}
                    )
                    pending = [
                        interrupt.value
                        for _, channel, interrupts in (
                            checkpoint.pending_writes if checkpoint else []
                        )
                        if channel == "__interrupt__"
                        for interrupt in interrupts
                    ]
                    if pending:
                        await pending_approval(app, owner, rid, pending[0])
                yield
                if app.state.running_tasks:
                    for task in list(app.state.running_tasks):
                        task.cancel()
                    await asyncio.gather(
                        *app.state.running_tasks, return_exceptions=True
                    )
        finally:
            if hasattr(app.state.gateway, "aclose"):
                await app.state.gateway.aclose()
            await semantic_index.close()
            await engine.dispose()
            lock.unlink(missing_ok=True)

    app = FastAPI(title="Campus Assistant", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, exc):
        # Pydantic can attach the entire submitted object to model-validator
        # errors. Never echo passwords, model keys or private screenshot data.
        detail = [
            {k: error[k] for k in ("type", "loc", "msg") if k in error}
            for error in exc.errors()
        ]
        return JSONResponse({"detail": detail}, status_code=422)

    app.state.config, app.state.sessions = config, sessions
    app.state.gateway = ModelGateway(config)
    app.state.semantic_index = semantic_index

    async def get_db():
        # SQLite serializes short business transactions, including replay checks.
        async with sqlite_transaction(sessions) as db:
            yield db

    users, auth_backend = build_auth(config, get_db)
    current_user = users.current_user(active=True)
    from app.local_mode import (
        local_request_allowed,
        local_router,
        selected_user_dependency,
    )

    if config.app_mode == "local":
        current_user = selected_user_dependency(current_user, get_db)
        app.include_router(local_router(config, get_db, users, auth_backend))
        from app.local_tools import local_tools_router

        app.include_router(local_tools_router(config, current_user, get_db))
        app.state.local_session_lock = asyncio.Lock()
    app.state.get_db, app.state.current_user = get_db, current_user

    @app.middleware("http")
    async def csrf(request: Request, call_next):
        if config.app_mode == "local":
            if not local_request_allowed(request, config):
                return JSONResponse(
                    {"detail": "本地模式仅接受本机同源访问"}, status_code=403
                )
            if request.url.path.startswith("/api/auth/"):
                return JSONResponse({"detail": "本地模式无需账号登录"}, status_code=404)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            token = request.cookies.get("campus_csrf", "")
            supplied = request.headers.get("x-csrf-token", "")
            if (
                origin != config.public_origin
                or not token
                or not secrets.compare_digest(token, supplied)
            ):
                return JSONResponse({"detail": "CSRF 校验失败"}, status_code=403)
        if config.app_mode == "local" and request.url.path == "/api/local/session":
            async with app.state.local_session_lock:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(
        users.get_register_router(UserRead, UserCreate), prefix="/api/auth"
    )
    app.include_router(users.get_auth_router(auth_backend), prefix="/api/auth")

    @app.get("/api/csrf")
    def csrf_token(request: Request):
        token = request.cookies.get("campus_csrf") or secrets.token_urlsafe(32)
        response = JSONResponse({"csrf_token": token})
        response.set_cookie(
            "campus_csrf",
            token,
            secure=config.secure_cookie,
            samesite="lax",
            httponly=True,
        )
        return response

    from app.desktop_handoff import runtime_manifest
    from uuid import uuid4
    desktop_runtime = runtime_manifest(resource_root())
    desktop_instance = uuid4().hex

    @app.get("/api/healthz")
    def health():
        from app.launcher import service_identity

        return {
            **service_identity(config),
            **desktop_runtime,
            "instance_id": desktop_instance,
            "status": "ok",
            "capabilities": [
                "after-class-checkin",
                "calendar-course-entry",
                "pet-state",
                "schedule-reminders",
                "planning-constraints-once",
                "timetable-recognition",
                "timetable-text",
                "planning-today",
                "course-changes",
                "execution-timers-v1",
                "profiles-v1",
                "goals-v1",
                "weekly-review-v1",
                "planning-core-v1",
                "b-interaction-v1",
                "project-completion-v1",
                "desktop-workspace-v1",
                "desktop-import-bridge-v1",
            ],
            "model_configured": bool(config.text_model and config.model_api_key),
            "vision_configured": bool(config.vision_model and config.model_api_key),
            "scut_verified": bool(config.scut_adapter_path),
        }

    @app.get("/api/app-mode")
    def app_mode():
        return {"mode": config.app_mode}

    @app.get("/api/me", response_model=UserRead)
    async def me(user=Depends(current_user)):
        return user

    from app.campus_presets import (
        CAMPUS_PRESETS,
        CampusPreset,
        reconcile_settings_preset,
    )
    from app.contracts import ResourceView

    @app.get("/api/campus-presets", response_model=list[CampusPreset])
    def get_campus_presets(user=Depends(current_user)):
        return CAMPUS_PRESETS

    @app.get("/api/settings", response_model=ResourceView)
    async def get_settings(user=Depends(current_user), db=Depends(get_db)):
        return store.view(await store.settings(db, str(user.id)))

    @app.put("/api/settings", response_model=ResourceView)
    async def update_settings(
        body: SettingsUpdate,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        async def update():
            s = await store.settings(db, str(user.id))
            store.revision(s, body.revision)
            s.data = reconcile_settings_preset(
                s.data, body.data.model_dump(mode="json")
            )
            s.revision += 1
            return store.view(s)

        return await store.mutate(
            db, str(user.id), "settings", key, body.model_dump(mode="json"), update
        )

    app.include_router(business_router(get_db, current_user))
    app.include_router(browser_router(config, get_db, current_user))
    app.include_router(desktop_import_router(config, get_db, current_user))
    app.include_router(assignment_router(config, get_db, current_user))
    app.include_router(timetable_recognition_router(config, get_db, current_user))
    app.include_router(task_router(get_db, current_user))
    app.include_router(execution_router(get_db, current_user))
    app.include_router(timer_router(get_db, current_user, str(uuid4())))
    from app.memory_routes import memory_router
    app.include_router(memory_router(config, get_db, current_user))
    from app.knowledge_routes import knowledge_router
    from app.integrations_routes import integrations_router
    app.include_router(knowledge_router(config, get_db, current_user))
    from app.web_research import research_router
    app.include_router(research_router(config, get_db, current_user))
    from app.zotero_routes import zotero_router
    app.include_router(zotero_router(config, get_db, current_user))
    app.include_router(integrations_router(config, get_db, current_user))
    app.include_router(profile_router(get_db, current_user))
    app.include_router(goal_router(get_db, current_user))
    app.include_router(review_router(get_db, current_user))
    from app.conversation_constraint_routes import conversation_constraint_router
    from app.duration_suggestions_routes import duration_suggestions_router
    from app.goal_capacity_routes import goal_capacity_router
    from app.negotiation_routes import negotiation_router
    from app.proactive_routes import proactive_router

    app.include_router(duration_suggestions_router(get_db, current_user))
    from app.duration_generator import generator_router

    app.include_router(generator_router(get_db, current_user))
    app.include_router(conversation_constraint_router(get_db, current_user))
    app.include_router(goal_capacity_router(get_db, current_user))
    from app.study_types import study_type_router

    app.include_router(study_type_router(get_db, current_user))
    from app.semester_routes import semester_calendar_router

    app.include_router(semester_calendar_router(get_db, current_user))
    app.include_router(negotiation_router(get_db, current_user))
    app.include_router(proactive_router(get_db, current_user))
    app.include_router(planner_router(get_db, current_user))
    from app.planning_changes import changes_router

    app.include_router(changes_router(get_db, current_user))
    app.include_router(constraint_router(get_db, current_user))
    app.include_router(course_change_router(get_db, current_user))
    app.include_router(agent_router(get_db, current_user))
    app.include_router(pet_router(get_db, current_user))
    app.include_router(reminder_router(get_db, current_user))
    app.include_router(data_router(get_db, current_user))
    app.include_router(after_class_router(get_db, current_user))

    dist = resource_root() / "frontend" / "dist"
    if dist.is_dir():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path == "api" or path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(dist / "index.html")

    return app
