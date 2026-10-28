"""Owner-scoped profile aggregate, using the caller's existing transaction."""

from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from app import store
from app.db import Resource, now
from app.planning_history import record_change
from app.profile_contracts import ProfileData, ProfileReset, ProfileView, ProfileWrite


def profile_id(owner):
    return str(uuid5(NAMESPACE_URL, f"user-profile:{owner}"))


async def current_profile(db, owner):
    resource = await db.get(Resource, profile_id(owner))
    if resource and (resource.owner_id != owner or resource.kind != "user_profile"):
        raise HTTPException(404, "档案不存在")
    return resource


async def read_profile(db, owner) -> dict:
    resource = await current_profile(db, owner)
    settings = await store.rows(db, owner, "settings")
    return ProfileView(
        id=resource.id if resource else None,
        revision=resource.revision if resource else 0,
        source_revision=settings[0].revision if settings else 0,
        data=ProfileData.model_validate(resource.data) if resource else ProfileData(),
    ).model_dump(mode="json")


async def replace_profile(db, owner, body: ProfileWrite | ProfileReset) -> dict:
    resource = await current_profile(db, owner)
    if (resource.revision if resource else 0) != body.revision:
        raise HTTPException(409, "档案已在另一端更新，请刷新后重新校对")
    reset = isinstance(body, ProfileReset)
    data = ProfileData(
        **({} if reset else body.data.model_dump()),
        source="user",
        confirmed=True,
        updated_at=now(),
    ).model_dump(mode="json")
    if resource:
        resource.data = data
        resource.revision += 1
    else:
        resource = Resource(
            id=profile_id(owner), owner_id=owner, kind="user_profile", data=data
        )
        db.add(resource)
    await db.flush()
    await store.bump(db, owner)
    await record_change(
        db,
        owner,
        "profile_changed",
        resource.id,
        resource.revision,
        {
            "action": "reset" if reset else "replace",
            "profile_revision": resource.revision,
            "source_revision": (await store.settings(db, owner)).revision,
            "contract_version": "profile-v1",
        },
    )
    return await read_profile(db, owner)
