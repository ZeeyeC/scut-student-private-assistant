"""Owner-scoped shortcuts and durable delivery receipts for scheduled occurrences."""
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator

from app import store
from app.contracts import StrictModel
from app.db import Resource
from app.schedule import calendar_events


def now():
    return datetime.now(timezone.utc)


def record_id(owner, kind, key):
    return str(uuid5(NAMESPACE_URL, f'{owner}:{kind}:{key}'))


class Shortcut(StrictModel):
    event_id: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    revision: int = Field(default=0, ge=0)
    enabled: bool = True
    target_kind: Literal['none', 'website', 'file'] = 'none'
    target: str = Field(default='', max_length=4096)

    @model_validator(mode='after')
    def valid_target(self):
        if self.starts_at.tzinfo is None:
            raise ValueError('开始时间需要时区')
        self.target = self.target.strip()
        if self.target_kind == 'website':
            u = urlsplit(self.target)
            if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or any(ord(c) < 32 for c in self.target):
                raise ValueError('请填写完整的 http 或 https 网站地址')
        elif self.target_kind == 'file':
            if not PurePosixPath(self.target).is_absolute() or '\x00' in self.target:
                raise ValueError('请通过桌宠选择文件，或填写以 / 开头的本机完整路径')
        else:
            self.target = ''
        return self


async def occurrence(db, owner, event_id, starts_at):
    settings = await store.settings(db, owner)
    day = starts_at.astimezone(ZoneInfo(settings.data['timezone'])).date()
    result = await calendar_events(db, owner, day, day)
    event = next((e for e in result['events'] if e['id'] == event_id and datetime.fromisoformat(e['starts_at']) == starts_at), None)
    if not event:
        raise HTTPException(404, '日程已移除或时间已调整，请重新打开详情')
    return event


async def config_for(db, owner, event_id):
    row = await db.get(Resource, record_id(owner, 'schedule_shortcut', event_id))
    return {'revision': row.revision, **row.data} if row else {'revision': 0, 'enabled': True, 'target_kind': 'none', 'target': ''}


async def due_reminders(db, owner):
    current = now()
    settings = await store.settings(db, owner)
    tz = ZoneInfo(settings.data['timezone'])
    end = current + timedelta(minutes=5)
    result = await calendar_events(db, owner, current.astimezone(tz).date(), end.astimezone(tz).date())
    tasks = {r.id: r.data for r in await store.rows(db, owner, 'task')}
    blocks = {r.id: r.data for r in await store.rows(db, owner, 'plan_block')}
    reminders = []
    for e in result['events']:
        start = datetime.fromisoformat(e['starts_at'])
        if not current < start <= end:
            continue
        task = tasks.get(blocks.get(e['id'], {}).get('task_id'), {})
        if task.get('status') in ('completed', 'archived') or blocks.get(e['id'], {}).get('status') == 'completed':
            continue
        config = await config_for(db, owner, e['id'])
        if not config['enabled']:
            continue
        key = hashlib.sha256(f"{e['id']}:{start.isoformat()}".encode()).hexdigest()
        receipt = await db.get(Resource, record_id(owner, 'schedule_delivery', key))
        reminders.append({**e, 'key': key, 'announced': receipt is not None, 'target_kind': config['target_kind'], 'target': config['target']})
    return reminders


class Acknowledge(StrictModel):
    key: str = Field(min_length=64, max_length=64)


def reminder_router(get_db, current_user):
    router = APIRouter(prefix='/api')

    @router.get('/schedule-shortcut')
    async def get_shortcut(event_id: str, starts_at: datetime, user=Depends(current_user), db=Depends(get_db)):
        if starts_at.tzinfo is None:
            raise HTTPException(422, '开始时间需要时区')
        owner = str(user.id)
        await occurrence(db, owner, event_id, starts_at)
        return await config_for(db, owner, event_id)

    @router.put('/schedule-shortcut')
    async def save_shortcut(body: Shortcut, user=Depends(current_user), db=Depends(get_db)):
        owner = str(user.id)
        await occurrence(db, owner, body.event_id, body.starts_at)
        rid = record_id(owner, 'schedule_shortcut', body.event_id)
        row = await db.get(Resource, rid)
        if (row.revision if row else 0) != body.revision:
            raise HTTPException(409, '快捷方式已在另一端更新，请关闭详情后重新打开')
        data = body.model_dump(mode='json', exclude={'revision', 'starts_at'})
        if row:
            row.data = data
            row.revision += 1
        else:
            db.add(Resource(id=rid, owner_id=owner, kind='schedule_shortcut', data=data))
        await db.flush()
        return await config_for(db, owner, body.event_id)

    @router.get('/schedule-reminders')
    async def reminders(user=Depends(current_user), db=Depends(get_db)):
        return await due_reminders(db, str(user.id))

    @router.post('/schedule-reminders/ack')
    async def acknowledge(body: Acknowledge, user=Depends(current_user), db=Depends(get_db)):
        owner = str(user.id)
        rid = record_id(owner, 'schedule_delivery', body.key)
        if not await db.get(Resource, rid):
            if not any(e['key'] == body.key for e in await due_reminders(db, owner)):
                raise HTTPException(404, '提醒已过期')
            db.add(Resource(id=rid, owner_id=owner, kind='schedule_delivery', data={'key': body.key}))
        return {'saved': True}

    return router
