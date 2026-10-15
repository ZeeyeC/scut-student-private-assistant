from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase

from app.db import AccessToken, User


class UserRead(schemas.BaseUser[UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


def build_auth(config, get_db):
    async def user_db(db=Depends(get_db)):
        yield SQLAlchemyUserDatabase(db, User)

    class Manager(UUIDIDMixin, BaseUserManager[User, UUID]):
        async def validate_password(self, password, user):
            from fastapi_users.exceptions import InvalidPasswordException

            if len(password) < 12:
                raise InvalidPasswordException("密码至少 12 字符")

        async def create(self, *args, **kwargs):
            if not config.registration_enabled and config.app_mode == "shared":
                raise HTTPException(403, "注册已关闭，请联系部署者")
            return await super().create(*args, **kwargs)

    async def manager(database=Depends(user_db)):
        yield Manager(database)

    async def strategy(db=Depends(get_db)):
        yield DatabaseStrategy(
            SQLAlchemyAccessTokenDatabase(db, AccessToken), lifetime_seconds=86400 * 7
        )

    backend = AuthenticationBackend(
        name="cookie",
        transport=CookieTransport(
            cookie_name="campus_session",
            cookie_max_age=86400 * 7,
            cookie_secure=config.secure_cookie,
            cookie_samesite="lax",
        ),
        get_strategy=strategy,
    )
    users = FastAPIUsers[User, UUID](manager, [backend])
    return users, backend
