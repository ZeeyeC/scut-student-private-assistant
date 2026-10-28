"""Goal router factory; get_db must provide an atomic serialized transaction."""
from fastapi import APIRouter, Depends, Header
from app import goals, store
from app.goal_contracts import GoalCreate, GoalPatch, GoalView, GoalsView


def goal_router(get_db, current_user):
    router = APIRouter(prefix='/api')

    @router.get('/goals', response_model=GoalsView)
    async def read(user=Depends(current_user), db=Depends(get_db)):
        return await goals.read_goals(db, str(user.id))

    @router.post('/goals', response_model=GoalView)
    async def create(body: GoalCreate, key: str = Header(alias='Idempotency-Key'), user=Depends(current_user), db=Depends(get_db)):
        owner = str(user.id)
        return await store.mutate(db, owner, 'goal-create', key, body.model_dump(mode='json'),
                                  lambda: goals.create_goal(db, owner, body))

    @router.patch('/goals/{rid}', response_model=GoalView)
    async def patch(rid: str, body: GoalPatch, key: str = Header(alias='Idempotency-Key'), user=Depends(current_user), db=Depends(get_db)):
        owner = str(user.id)
        return await store.mutate(db, owner, f'goal-patch:{rid}', key, body.model_dump(exclude_unset=True, mode='json'),
                                  lambda: goals.patch_goal(db, owner, rid, body))

    return router
