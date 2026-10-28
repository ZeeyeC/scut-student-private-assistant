"""Durable goals. All writes share the caller's serialized transaction."""
from uuid import uuid4
from fastapi import HTTPException
from app import store
from app.db import Resource, now
from app.goal_contracts import GoalCreate, GoalData, GoalPatch, GoalValues, GoalView, GoalsView
from app.planning_history import record_change


async def source_revision(db, owner):
    settings = await store.rows(db, owner, 'settings')
    return settings[0].revision if settings else 0


async def goal_view(db, owner, resource):
    references = []
    for subtask in resource.data['subtasks']:
        if not subtask['task_id']:
            continue
        task = await db.get(Resource, subtask['task_id'])
        available = bool(task and task.owner_id == owner and task.kind == 'task')
        references.append({
            'subtask_id': subtask['id'], 'task_id': subtask['task_id'], 'available': available,
            'revision': task.revision if available else None,
            'title': task.data.get('title') if available else None,
            'status': task.data.get('status') if available else None,
        })
    return GoalView(id=resource.id, revision=resource.revision,
                    source_revision=await source_revision(db, owner), data=resource.data,
                    references=references).model_dump(mode='json')


async def read_goals(db, owner):
    return GoalsView(source_revision=await source_revision(db, owner),
                     goals=[await goal_view(db, owner, r) for r in await store.rows(db, owner, 'goal')]).model_dump(mode='json')


async def normalize_subtasks(db, owner, subtasks, previous, revision, history):
    existing = {s['id']: s for s in previous}
    normalized = []
    for sub in subtasks:
        value = sub.model_dump(mode='json')
        if sub.id and sub.id not in existing:
            raise HTTPException(422, '子任务标识不属于当前目标')
        if sub.task_id and (not sub.id or existing[sub.id]['task_id'] != sub.task_id):
            await store.owned(db, owner, sub.task_id, 'task')
        value['id'] = sub.id or str(uuid4())
        if sub.status == 'completed' and (not sub.id or existing[sub.id]['status'] != 'completed'):
            history.append({
                'subtask_id': value['id'], 'title': value['title'],
                'estimated_minutes': value['estimated_minutes'], 'task_id': value['task_id'],
                'completed_at': now().isoformat(), 'goal_revision': revision,
            })
        normalized.append(value)
    return normalized


async def changed(db, owner, resource, action):
    await db.flush()
    await store.bump(db, owner)
    await record_change(db, owner, 'goal_changed', resource.id, resource.revision, {
        'action': action, 'goal_revision': resource.revision,
        'source_revision': await source_revision(db, owner),
        'contract_version': 'goals-v1', 'paused': resource.data['paused'],
    })
    return await goal_view(db, owner, resource)


async def create_goal(db, owner, body: GoalCreate):
    history = []
    data = body.model_dump(exclude={'revision'}, mode='json')
    data['subtasks'] = await normalize_subtasks(db, owner, body.subtasks, [], 1, history)
    data = GoalData(**data, updated_at=now(), completion_history=history).model_dump(mode='json')
    resource = Resource(id=str(uuid4()), owner_id=owner, kind='goal', data=data)
    db.add(resource)
    return await changed(db, owner, resource, 'create')


async def patch_goal(db, owner, rid, body: GoalPatch):
    resource = await store.owned(db, owner, rid, 'goal')
    store.revision(resource, body.revision)
    previous = resource.data
    values = {k: previous[k] for k in GoalValues.model_fields}
    values.update(body.model_dump(exclude={'revision'}, exclude_unset=True, mode='json'))
    validated = GoalValues.model_validate(values)
    history = [dict(fact) for fact in previous['completion_history']]
    values = validated.model_dump(mode='json')
    values['subtasks'] = await normalize_subtasks(db, owner, validated.subtasks, previous['subtasks'], resource.revision + 1, history)
    resource.data = GoalData(**values, updated_at=now(), completion_history=history).model_dump(mode='json')
    resource.revision += 1
    action = 'pause' if body.paused is True else 'resume' if body.paused is False else 'edit'
    return await changed(db, owner, resource, action)
