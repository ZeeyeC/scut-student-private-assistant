from datetime import datetime, timedelta, timezone

import pytest

from app import schedule_reminders as reminders
from tests.test_foundation import make_client, register_login


def event(c, h, start='2026-10-17T12:00:00+00:00'):
    e = c.post('/api/fixed-events', json={'title':'做实验', 'starts_at':start, 'ends_at':(datetime.fromisoformat(start)+timedelta(hours=1)).isoformat()}, headers={**h,'Idempotency-Key':start}).json()
    return {'event_id': e['id'], 'starts_at': start, 'revision':0, 'enabled':True, 'target_kind':'website', 'target':'https://example.com/homework'}


def test_boundary_delivery_persistence_and_shortcut(tmp_path, monkeypatch):
    clock = [datetime(2026,10,17,11,54,59,tzinfo=timezone.utc)]
    monkeypatch.setattr(reminders,'now',lambda:clock[0])
    with make_client(tmp_path) as c:
        h = register_login(c)
        body = event(c,h)
        saved = c.put('/api/schedule-shortcut',json=body,headers=h)
        assert saved.status_code == 200 and saved.json()['revision'] == 1
        assert c.get('/api/schedule-reminders').json() == []
        clock[0] += timedelta(seconds=1)
        due = c.get('/api/schedule-reminders').json()
        assert len(due)==1 and due[0]['target']==body['target'] and not due[0]['announced']
        for _ in range(2):
            assert c.post('/api/schedule-reminders/ack',json={'key':due[0]['key']},headers=h).status_code==200
        assert c.get('/api/schedule-reminders').json()[0]['announced']
        clock[0] += timedelta(minutes=5)
        assert c.get('/api/schedule-reminders').json()==[]
    clock[0] -= timedelta(minutes=1)
    with make_client(tmp_path) as c:
        token=c.get('/api/csrf').json()['csrf_token']
        assert c.post('/api/auth/login',data={'username':'alice@example.com','password':'Student!Password2026'},headers={'Origin':'http://testserver','X-CSRF-Token':token}).status_code==204
        assert c.get('/api/schedule-reminders').json()[0]['announced']


@pytest.mark.parametrize('kind,target', [('website','javascript:alert(1)'),('website','file:///tmp/a'),('website','https://u:p@example.com'),('file','relative.pdf'),('file','~/a')])
def test_invalid_targets(tmp_path,kind,target):
    with make_client(tmp_path) as c:
        h=register_login(c); body=event(c,h)
        assert c.put('/api/schedule-shortcut',json={**body,'target_kind':kind,'target':target},headers=h).status_code==422


def test_owner_revision_disable_and_removed_event(tmp_path,monkeypatch):
    monkeypatch.setattr(reminders,'now',lambda:datetime(2026,10,17,11,56,tzinfo=timezone.utc))
    with make_client(tmp_path) as c:
        h=register_login(c); body=event(c,h)
        saved=c.put('/api/schedule-shortcut',json={**body,'target_kind':'file','target':'/tmp/中文 作业.pdf'},headers=h).json()
        assert saved['target']=='/tmp/中文 作业.pdf'
        assert c.put('/api/schedule-shortcut',json=body,headers=h).status_code==409
        assert c.put('/api/schedule-shortcut',json={**body,'revision':1,'enabled':False},headers=h).status_code==200
        assert c.get('/api/schedule-reminders').json()==[]
        assert c.get('/api/schedule-shortcut',params={'event_id':body['event_id'],'starts_at':'2026-10-17T13:00:00+00:00'}).status_code==404
        existing=c.get('/api/fixed-events').json()[0]
        assert c.request('DELETE','/api/fixed-events/'+body['event_id'],json={'revision':existing['revision']},headers={**h,'Idempotency-Key':'remove'}).status_code==200
        assert c.get('/api/schedule-reminders').json()==[]
        assert c.put('/api/schedule-shortcut',json={**body,'revision':2},headers=h).status_code==404
        c.post('/api/auth/logout',headers=h)
        h2=register_login(c,'bob@example.com')
        assert c.get('/api/schedule-reminders').json()==[]
        assert c.put('/api/schedule-shortcut',json=body,headers=h2).status_code==404
        assert c.get('/api/schedule-shortcut',params={'event_id':body['event_id'],'starts_at':body['starts_at']}).status_code==404


def test_cross_midnight_window(tmp_path,monkeypatch):
    monkeypatch.setattr(reminders,'now',lambda:datetime.fromisoformat('2026-10-17T23:58:00+08:00'))
    with make_client(tmp_path) as c:
        h=register_login(c); event(c,h,'2026-10-18T00:02:00+08:00')
        assert len(c.get('/api/schedule-reminders').json())==1
