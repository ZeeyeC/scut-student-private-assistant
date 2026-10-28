"""Goal API uses a real isolated SQLite database, including transaction failures."""
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.db import Base, Resource, Receipt


def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/goals.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    @asynccontextmanager
    async def lifespan(app):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
        await engine.dispose()
    app = FastAPI(lifespan=lifespan)
    app.state.sessions = sessions
    async def db_session():
        async with sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    async def user(x_test_owner: str | None = Header(default=None)):
        if not x_test_owner:
            raise HTTPException(401, "login required")
        return SimpleNamespace(id=x_test_owner)
    from app.goal_routes import goal_router
    app.include_router(goal_router(db_session, user))
    return TestClient(app)


def headers(key="create", owner="alice"):
    return {"X-Test-Owner": owner, "Idempotency-Key": key}


def body(**changes):
    result = {"revision": 0, "title": "练习英语", "description": "每周阅读", "deadline": None,
              "weekly_budget_minutes": 0, "priority": 2, "load_category": "study",
              "allowed_adjustment": "ask", "subtasks": [{"title": "读第一章", "estimated_minutes": 20}]}
    result.update(changes)
    return result


def rows(c, kind=None, model=Resource):
    async def read():
        async with c.app.state.sessions() as db:
            query = select(model)
            if kind:
                query = query.where(Resource.kind == kind)
            return list((await db.scalars(query)).all())
    return c.portal.call(read)


def test_create_unknown_capacity_zero_budget_idempotency_and_no_arrangements(tmp_path):
    with client(tmp_path) as c:
        assert c.get('/api/goals').status_code == 401
        assert c.get('/api/goals', headers=headers()).json()['goals'] == []
        assert rows(c) == []
        first = c.post('/api/goals', headers=headers(), json=body())
        assert first.status_code == 200, first.text
        goal = first.json()
        assert goal['revision'] == 1
        assert goal['source_revision'] == 2
        assert goal['contract_version'] == 'goals-v1'
        assert goal['data']['confirmed'] is True and goal['data']['source'] == 'user'
        assert goal['data']['weekly_budget_minutes'] == 0
        assert goal['data']['deadline'] is None and goal['data']['paused'] is False
        assert goal['capacity'] == {'status': 'unknown', 'weekly_available_minutes': None, 'integration_status': 'pending'}
        assert goal['arrangements'] == []
        assert c.post('/api/goals', headers=headers(), json=body()).json() == goal
        assert c.post('/api/goals', headers=headers(), json=body(title='别的')).status_code == 409
        assert len(rows(c, 'goal')) == len(rows(c, 'planning_event')) == len(rows(c, model=Receipt)) == 1
        assert rows(c, 'planning_event')[0].data['event_type'] == 'goal_changed'
        assert rows(c, 'task') == rows(c, 'plan') == []
        assert c.get('/api/goals', headers=headers()).json()['goals'] == [goal]


def test_edit_pause_resume_retains_completed_facts_and_stable_subtasks(tmp_path):
    with client(tmp_path) as c:
        goal = c.post('/api/goals', headers=headers(), json=body()).json()
        rid = goal['id']; sub = goal['data']['subtasks'][0]
        assert sub['id'] and sub['status'] == 'open'
        patch = {'revision': 1, 'deadline': '2026-12-01T18:00:00+08:00', 'subtasks': [{**{k: sub[k] for k in ('id','title','status','estimated_minutes','task_id')}, 'status': 'completed'}]}
        completed = c.patch(f'/api/goals/{rid}', headers=headers('done'), json=patch).json()
        assert completed['data']['subtasks'][0]['id'] == sub['id']
        facts = completed['data']['completion_history']
        assert len(facts) == 1 and facts[0]['subtask_id'] == sub['id']
        assert facts[0]['title'] == sub['title'] and facts[0]['completed_at']
        paused = c.patch(f'/api/goals/{rid}', headers=headers('pause'), json={'revision': 2, 'paused': True, 'title': '新标题', 'subtasks': []}).json()
        assert paused['data']['paused'] is True and paused['data']['completion_history'] == facts
        assert paused['arrangements'] == []
        assert c.patch(f'/api/goals/{rid}', headers=headers('pause'), json={'revision': 2, 'paused': True, 'title': '新标题', 'subtasks': []}).json() == paused
        assert c.patch(f'/api/goals/{rid}', headers=headers('stale'), json={'revision': 2, 'paused': False}).status_code == 409
        resumed = c.patch(f'/api/goals/{rid}', headers=headers('resume'), json={'revision': 3, 'paused': False}).json()
        assert resumed['data']['paused'] is False and resumed['data']['completion_history'] == facts
        assert len(rows(c, 'planning_event')) == 4
        assert rows(c, 'task') == rows(c, 'plan') == []
    with client(tmp_path) as c:
        loaded = c.get('/api/goals', headers=headers()).json()['goals'][0]
        assert loaded == resumed


def test_association_and_owner_checks(tmp_path):
    with client(tmp_path) as c:
        async def seed():
            async with c.app.state.sessions() as db:
                db.add_all([Resource(id='owned', owner_id='alice', kind='task', data={'title':'真实任务','status':'completed'}), Resource(id='other', owner_id='bob', kind='task', data={'title':'私人'}), Resource(id='wrong-kind', owner_id='alice', kind='course', data={})])
                await db.commit()
        c.portal.call(seed)
        for task in ('other', 'wrong-kind', 'missing'):
            assert c.post('/api/goals', headers=headers(task), json=body(subtasks=[{'title':'关联','estimated_minutes':5,'task_id':task}])).status_code == 404
        goal = c.post('/api/goals', headers=headers(), json=body(subtasks=[{'title':'关联','estimated_minutes':5,'task_id':'owned'}])).json()
        assert goal['references'] == [{'subtask_id':goal['data']['subtasks'][0]['id'],'task_id':'owned','available':True,'revision':1,'title':'真实任务','status':'completed'}]
        assert c.get('/api/goals', headers=headers(owner='bob')).json()['goals'] == []
        assert c.patch('/api/goals/'+goal['id'], headers=headers('other','bob'), json={'revision':1,'paused':True}).status_code == 404
        assert c.patch('/api/goals/'+goal['id'], headers=headers('bad-sub'), json={'revision':1,'subtasks':[{'id':'invented','title':'fake','estimated_minutes':1}]}).status_code == 422
        assert len(rows(c, 'goal')) == 1


@pytest.mark.parametrize('changes', [
    {'revision':1}, {'title':'  '}, {'weekly_budget_minutes':-1}, {'weekly_budget_minutes':True},
    {'weekly_budget_minutes':1.5}, {'weekly_budget_minutes':'60'}, {'priority':0}, {'priority':True},
    {'load_category':'capacity'}, {'allowed_adjustment':'auto'}, {'deadline':'2026-12-01T12:00:00'},
    {'paused':None}, {'confirmed':False}, {'capacity':{'status':'known'}},
    {'subtasks':[{'title':'','estimated_minutes':2}]}, {'subtasks':[{'title':'x','estimated_minutes':-1}]},
])
def test_invalid_goals_have_no_effects(tmp_path, changes):
    with client(tmp_path) as c:
        assert c.post('/api/goals', headers=headers(), json=body(**changes)).status_code == 422
        assert rows(c) == rows(c, model=Receipt) == []


def test_patch_null_and_duplicate_ids_rejected_and_rollback(tmp_path, monkeypatch):
    from app import goals
    with client(tmp_path) as c:
        assert c.post('/api/goals', json=body(), headers={'X-Test-Owner':'alice'}).status_code == 422
        goal = c.post('/api/goals', headers=headers(), json=body()).json()
        rid = goal['id']; sub = goal['data']['subtasks'][0]
        for change in ({'title':None}, {'weekly_budget_minutes':None}, {'subtasks':None}, {'subtasks':[sub, sub]}):
            assert c.patch('/api/goals/'+rid, headers=headers('invalid'), json={'revision':1, **change}).status_code == 422
        async def fail(*args, **kwargs):
            raise RuntimeError('synthetic goal event failure')
        monkeypatch.setattr(goals, 'record_change', fail)
        with pytest.raises(RuntimeError, match='synthetic goal event'):
            c.patch('/api/goals/'+rid, headers=headers('fail'), json={'revision':1,'paused':True})
        assert c.get('/api/goals', headers=headers()).json()['goals'] == [goal]
        assert len(rows(c, model=Receipt)) == len(rows(c, 'planning_event')) == 1


def test_strict_revisions_and_nullable_deadline_and_stale_reference(tmp_path):
    with client(tmp_path) as c:
        for revision in (False, True, '0', 0.0):
            assert c.post('/api/goals', headers=headers('bad-rev'), json=body(revision=revision)).status_code == 422
        async def seed():
            async with c.app.state.sessions() as db:
                db.add(Resource(id='soon-deleted',owner_id='alice',kind='task',data={'title':'旧任务'}))
                await db.commit()
        c.portal.call(seed)
        goal = c.post('/api/goals',headers=headers(),json=body(deadline='2026-12-01T18:00:00+08:00',subtasks=[{'title':'引用','estimated_minutes':5,'task_id':'soon-deleted'}])).json()
        async def remove():
            async with c.app.state.sessions() as db:
                await db.delete(await db.get(Resource,'soon-deleted'))
                await db.commit()
        c.portal.call(remove)
        loaded = c.get('/api/goals',headers=headers()).json()['goals'][0]
        assert loaded['references'][0]['available'] is False
        assert loaded['references'][0]['title'] is None
        patched = c.patch('/api/goals/'+goal['id'],headers=headers('pause'),json={'revision':1,'paused':True,'deadline':None})
        assert patched.status_code == 200, patched.text
        assert patched.json()['data']['deadline'] is None
        assert patched.json()['data']['subtasks'][0]['task_id'] == 'soon-deleted'
