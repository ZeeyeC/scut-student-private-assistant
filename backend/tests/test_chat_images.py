import io
import json
import threading
import time

from PIL import Image
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tests.test_agent import ToolModel, wait_run
from tests.test_foundation import make_client, register_login


class ImageVision:
    def __init__(self, fail=False, gate=None):
        self.calls = 0
        self.fail = fail
        self.gate = gate

    async def extract_assignments(self, *args):
        self.calls += 1
        if self.gate:
            import asyncio
            while not self.gate.is_set():
                await asyncio.sleep(.01)
        if self.fail:
            raise TimeoutError('synthetic provider failure')
        return {'items': [{'title': title, 'requirements': ['完成练习'],
                           'evidence': [{'field': 'title', 'text': title}],
                           'uncertain_fields': ['due_at']} for title in ['高数作业', '英语作业']]}


class ImageModel(ToolModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1]
        if isinstance(last, ToolMessage) and last.name == 'list_assignment_drafts':
            draft = json.loads(last.content)[0]
            tool = {'name': 'update_assignment_draft', 'id': 'image-correction', 'type': 'tool_call',
                    'args': {'draft_id': draft['id'], 'revision': draft['revision'], 'item_index': 1,
                             'changes': {'title': '英语听力', 'due_at': '2026-11-06T20:00:00+08:00'}}}
        elif not isinstance(last, ToolMessage) and '修改第二项' in str(last.content):
            tool = {'name': 'list_assignment_drafts', 'id': 'image-list', 'type': 'tool_call', 'args': {}}
        else:
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=[tool]))])


def post(c, h, path, body, key):
    return c.post('/api' + path, json=body, headers={**h, 'Idempotency-Key': key})


def upload(c, h, key='asset'):
    out = io.BytesIO(); Image.new('RGB', (80, 40), 'white').save(out, format='PNG')
    response = c.post('/api/assets', files={'file': ('作业.png', out.getvalue(), 'image/png')},
                      headers={**h, 'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    return response.json()['id']


def setup(c, h, vision):
    c.app.state.gateway = vision
    c.app.state.agent_model_factory = lambda: ImageModel()
    return post(c, h, '/agent/threads', {}, 'thread').json()['id']


def test_image_recognition_replay_correction_and_explicit_save(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c); vision = ImageVision(); tid = setup(c, h, vision); aid = upload(c, h)
        body = {'thread_id': tid, 'attachment': {'asset_id': aid, 'consent': True, 'reference_time': '2026-10-30T19:00:00+08:00'}}
        response = post(c, h, '/agent/runs', body, 'image-run'); assert response.status_code == 200, response.text
        rid = response.json()['id']; run = wait_run(c, rid); assert run['data']['status'] == 'done', run
        assert post(c, h, '/agent/runs', body, 'image-run').json()['id'] == rid
        assert vision.calls == 1 and c.get('/api/tasks').json() == []
        drafts = c.get('/api/drafts').json(); assert len(drafts) == 1
        draft = drafts[0]; assert draft['data']['payload']['asset_id'] == aid
        assert draft['data']['source']['thread_id'] == tid
        other_asset = upload(c, h, 'other-asset')
        replaced = {**draft['data']['payload'], 'asset_id': other_asset}
        assert c.put('/api/drafts/' + draft['id'], json={'revision': draft['revision'], 'payload': replaced}, headers={**h, 'Idempotency-Key': 'reject-replace'}).status_code == 422
        events = c.get(f'/api/agent/runs/{rid}/events').text
        assert 'asset_id' in events and 'base64' not in events
        follow = post(c, h, '/agent/runs', {'thread_id': tid, 'message': '修改第二项'}, 'correction').json()
        assert wait_run(c, follow['id'])['data']['status'] == 'done'
        changed = c.get('/api/drafts/' + draft['id']).json()
        items = changed['data']['payload']['items']
        assert items[0] == draft['data']['payload']['items'][0]
        assert items[1]['title'] == '英语听力' and items[1]['due_at'].startswith('2026-11-06T20:00')
        assert items[1]['evidence'] == draft['data']['payload']['items'][1]['evidence']
        assert changed['data']['payload']['asset_id'] == aid
        saved = post(c, h, '/drafts/' + draft['id'] + '/confirm', {'revision': changed['revision']}, 'save')
        assert saved.status_code == 200, saved.text
        assert len(c.get('/api/tasks').json()) == 2


def test_image_consent_owner_thread_and_type_validation(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c); tid = setup(c, h, ImageVision()); aid = upload(c, h)
        assert post(c, h, '/agent/runs', {'thread_id': tid, 'attachment': {'asset_id': aid, 'consent': False}}, 'no-consent').status_code == 422
        assert post(c, h, '/agent/runs', {'thread_id': tid, 'attachment': {'asset_id': aid, 'consent': True, 'reference_time': '2026-11-01T12:00:00'}}, 'naive-reference').status_code == 422
        out = io.BytesIO(); Image.new('RGB', (10, 10), 'white').save(out, format='PNG')
        timetable = c.post('/api/timetable-assets', files={'file': ('课表.png', out.getvalue(), 'image/png')}, headers={**h, 'Idempotency-Key': 'timetable-asset'}).json()
        assert post(c, h, '/agent/runs', {'thread_id': tid, 'attachment': {'asset_id': timetable['id'], 'consent': True}}, 'reject-timetable').status_code == 422
        run = post(c, h, '/agent/runs', {'thread_id': tid, 'attachment': {'asset_id': aid, 'consent': True}}, 'first').json()
        wait_run(c, run['id'])
        other = post(c, h, '/agent/threads', {}, 'other').json()['id']
        assert post(c, h, '/agent/runs', {'thread_id': other, 'attachment': {'asset_id': aid, 'consent': True}}, 'rebind').status_code == 409
        assert post(c, h, '/agent/runs', {'thread_id': other, 'attachment': {'asset_id': 'missing', 'consent': True}}, 'missing').status_code == 404
        # A different logged-in owner cannot reference this owner's image.
        h2 = register_login(c, 'second@example.com')
        tid2 = post(c, h2, '/agent/threads', {}, 'thread2').json()['id']
        assert post(c, h2, '/agent/runs', {'thread_id': tid2, 'attachment': {'asset_id': aid, 'consent': True}}, 'cross-owner').status_code == 404


def test_failed_image_retry_reuses_run_and_creates_one_draft(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c); vision = ImageVision(fail=True); tid = setup(c, h, vision); aid = upload(c, h)
        run = post(c, h, '/agent/runs', {'thread_id': tid, 'attachment': {'asset_id': aid, 'consent': True}}, 'run').json()
        run = wait_run(c, run['id']); assert run['data']['status'] == 'failed'
        assert c.get('/api/drafts').json() == []
        vision.fail = False
        response = post(c, h, '/agent/runs/' + run['id'] + '/image/retry', {'revision': run['revision']}, 'retry')
        assert response.status_code == 200, response.text
        assert wait_run(c, run['id'])['data']['status'] == 'done'
        assert len(c.get('/api/drafts').json()) == 1 and vision.calls == 2


def test_cancel_image_suppresses_late_result(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c); gate = threading.Event(); vision = ImageVision(gate=gate); tid = setup(c, h, vision); aid = upload(c, h)
        run = post(c, h, '/agent/runs', {'thread_id': tid, 'attachment': {'asset_id': aid, 'consent': True}}, 'run').json()
        for _ in range(100):
            if vision.calls: break
            time.sleep(.01)
        latest = c.get('/api/agent/runs/' + run['id']).json()
        cancelled = post(c, h, '/agent/runs/' + run['id'] + '/image/cancel', {'revision': latest['revision']}, 'cancel')
        assert cancelled.status_code == 200, cancelled.text
        gate.set()
        assert c.get('/api/agent/runs/' + run['id']).json()['data']['status'] == 'cancelled'
        assert c.get('/api/drafts').json() == []
        assert 'cancelled' in c.get('/api/agent/runs/' + run['id'] + '/events').text


def test_interrupted_image_can_resume_explicitly_after_restart(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c); gate = threading.Event(); vision = ImageVision(gate=gate)
        tid = setup(c, h, vision); aid = upload(c, h)
        run = post(c, h, '/agent/runs', {'thread_id': tid, 'attachment': {'asset_id': aid, 'consent': True}}, 'run').json()
        for _ in range(100):
            if vision.calls: break
            time.sleep(.01)
        assert vision.calls == 1
    with make_client(tmp_path) as c:
        csrf = c.get('/api/csrf').json()['csrf_token']; h = {'X-CSRF-Token': csrf, 'Origin': 'http://testserver'}
        assert c.post('/api/auth/login', data={'username': 'alice@example.com', 'password': 'Student!Password2026'}, headers=h).status_code == 204
        vision = ImageVision(); c.app.state.gateway = vision; c.app.state.agent_model_factory = lambda: ImageModel()
        latest = c.get('/api/agent/runs/' + run['id']).json()
        assert latest['data']['status'] == 'failed' and vision.calls == 0
        assert post(c, h, '/agent/runs/' + run['id'] + '/image/retry', {'revision': latest['revision']}, 'retry-restart').status_code == 200
        assert wait_run(c, run['id'])['data']['status'] == 'done'
        assert len(c.get('/api/drafts').json()) == 1
