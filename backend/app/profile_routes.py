"""Profile routes. The supplied get_db must own an atomic serialized transaction."""

from fastapi import APIRouter, Depends, Header

from app import profiles, store
from app.profile_contracts import ProfileReset, ProfileView, ProfileWrite


def profile_router(get_db, current_user):
    router = APIRouter(prefix="/api")

    @router.get("/profile", response_model=ProfileView)
    async def read(user=Depends(current_user), db=Depends(get_db)):
        return await profiles.read_profile(db, str(user.id))

    @router.put("/profile", response_model=ProfileView)
    async def replace(
        body: ProfileWrite,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "profile-replace",
            key,
            body.model_dump(mode="json"),
            lambda: profiles.replace_profile(db, owner, body),
        )

    @router.post("/profile/reset", response_model=ProfileView)
    async def reset(
        body: ProfileReset,
        key: str = Header(alias="Idempotency-Key"),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        owner = str(user.id)
        return await store.mutate(
            db,
            owner,
            "profile-reset",
            key,
            body.model_dump(mode="json"),
            lambda: profiles.replace_profile(db, owner, body),
        )

    return router
