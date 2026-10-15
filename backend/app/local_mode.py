"""Loopback-only onboarding using the existing FastAPI Users session strategy."""

import ipaddress
import secrets
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth import UserCreate
from app.db import AccessToken, LocalProfile, Resource, User


def local_request_allowed(request, config):
    try:
        origin = urlsplit(config.public_origin)
        return (
            ipaddress.ip_address(request.client.host).is_loopback
            and origin.hostname in {"127.0.0.1", "localhost", "::1"}
            and request.headers.get("host") == origin.netloc
            and request.headers.get("origin", config.public_origin)
            == config.public_origin
        )
    except (ValueError, AttributeError):
        return False


class ProfileChoice(BaseModel):
    profile_id: UUID | None = None
    create_new: bool = False


def local_router(config, get_db, users, auth_backend):
    router = APIRouter(prefix="/api/local")

    @router.get("/status")
    async def status(db=Depends(get_db)):
        selected = await db.get(LocalProfile, 1)
        profiles = []
        if not selected:
            for user in await db.scalars(select(User).where(User.is_active.is_(True))):
                count = await db.scalar(
                    select(func.count())
                    .select_from(Resource)
                    .where(Resource.owner_id == str(user.id))
                )
                profiles.append(
                    {"id": str(user.id), "email": user.email, "resource_count": count}
                )
        return {
            "selected": bool(selected),
            "needs_selection": not selected and bool(profiles),
            "profiles": profiles,
        }

    @router.post("/session")
    async def session(
        body: ProfileChoice, db=Depends(get_db), manager=Depends(users.get_user_manager)
    ):
        chosen = await db.get(LocalProfile, 1)
        if chosen:
            if body.create_new or (
                body.profile_id and body.profile_id != chosen.owner_id
            ):
                raise HTTPException(409, "已选定本地资料，不能在启动时切换或覆盖")
            user = await db.get(User, chosen.owner_id)
        else:
            existing = list(
                await db.scalars(select(User).where(User.is_active.is_(True)))
            )
            if body.profile_id:
                user = next((u for u in existing if u.id == body.profile_id), None)
                if not user:
                    raise HTTPException(404, "未找到该本地资料")
            elif existing and not body.create_new:
                raise HTTPException(
                    409, "检测到已有资料，请选择继续使用或新建；原数据不会删除"
                )
            else:
                user = await manager.create(
                    UserCreate(
                        email=f"local-{uuid4().hex}@example.com",
                        password=secrets.token_urlsafe(32),
                    ),
                    safe=True,
                )
                # FastAPI Users commits internally; re-enter the serialized transaction.
                from sqlalchemy import text

                await db.execute(text("BEGIN IMMEDIATE"))
            db.add(LocalProfile(id=1, owner_id=user.id))
        if not user or not user.is_active:
            raise HTTPException(409, "本地资料不可用，原数据已保留")
        strategy = DatabaseStrategy(
            SQLAlchemyAccessTokenDatabase(db, AccessToken), lifetime_seconds=86400 * 7
        )
        token = await strategy.write_token(user)
        return await auth_backend.transport.get_login_response(token)

    return router


def selected_user_dependency(authenticated, get_db):
    async def selected(user=Depends(authenticated), db=Depends(get_db)):
        profile = await db.get(LocalProfile, 1)
        if not profile or profile.owner_id != user.id:
            raise HTTPException(401, "请打开本地助手建立会话")
        return user

    return selected
