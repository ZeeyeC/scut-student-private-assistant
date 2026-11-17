from datetime import datetime

from tests.test_after_class import clock, opened, seed, submit, write
from tests.test_foundation import make_client, register_login


def lesson(c):
    events = c.get('/api/calendar-events?start=2026-10-14&end=2026-10-14').json()['events']
    event = next(e for e in events if e['kind'] == 'course')
    return {'course_id': event['course_id'], 'original_date': event['original_date']}


def draft(c, h, ref, **patch):
    return write(c, h, '/api/drafts/assignment', {'items': [{
        'title': '补记练习', 'requirements': ['完成习题'],
        'course_occurrence': ref, 'estimated_minutes': 45, **patch,
    }]})


def confirm(c, h, d, key=None):
    return write(c, h, f"/api/drafts/{d['id']}/confirm", {'revision': d['revision']}, key=key)


def test_history_exits_automatic_queue_but_manual_date_restores_draft(tmp_path, monkeypatch):
    current = clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        first = opened(c, h)
        saved = write(c, h, f"/api/after-class/{first['review']['id']}/draft", {
            'revision': first['review']['revision'], 'answers': [{
                'course_key': first['courses'][0]['key'], 'status': 'homework',
                'items': [{'content': '保留的历史作业', 'estimated_minutes': 45}],
            }],
        }, 'put')
        assert saved.status_code == 200
        current[0] = datetime.fromisoformat('2026-10-17T19:00:00+08:00')
        assert opened(c, h)['due'] is False
        manual = write(c, h, '/api/after-class/open', {'date': '2026-10-14'}).json()
        assert manual['date'] == '2026-10-14'
        assert manual['review']['data']['draft_answers'][0]['items'][0]['content'] == '保留的历史作业'
        assert manual['automatic'] is False


def test_occurrence_assignment_confirm_is_idempotent_and_creates_step(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        ref = lesson(c)
        response = draft(c, h, ref); assert response.status_code == 200, response.text
        d = response.json()
        assert c.get('/api/tasks').json() == []
        first = confirm(c, h, d, 'save-once'); assert first.status_code == 200, first.text
        assert confirm(c, h, d, 'save-once').json() == first.json()
        tasks = c.get('/api/tasks').json(); assert len(tasks) == 1
        task = tasks[0]
        assert task['data']['course_occurrence'] == ref
        assert task['data']['course_id'] == ref['course_id']
        assert task['data']['course_occurrence_snapshot']['original_date'] == '2026-10-14'
        assert task['data']['due_at'] is None
        steps = c.get(f"/api/tasks/{task['id']}/steps").json()
        assert len(steps) == 1 and steps[0]['data']['estimated_minutes'] == 45
        assert c.get('/api/plan-blocks').json() == []


def test_changed_or_cancelled_occurrence_cannot_confirm_old_draft(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        ref = lesson(c); response = draft(c, h, ref)
        assert response.status_code == 200, response.text
        d = response.json()
        assert write(c, h, '/api/calendar-exceptions', {
            'course_id': ref['course_id'], 'date': ref['original_date'], 'cancelled': True,
        }).status_code == 200
        assert confirm(c, h, d).status_code == 409
        assert c.get('/api/tasks').json() == []
        assert draft(c, h, ref).status_code == 409


def test_occurrence_ownership_and_source_course_consistency(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        ref = lesson(c)
        another = next(r for r in c.get('/api/courses').json() if r['id'] != ref['course_id'])
        assert draft(c, h, ref, course_id=another['id']).status_code == 422
        assert draft(c, h, {**ref, 'original_date': '2026-10-15'}).status_code == 409
        c.post('/api/auth/logout', headers=h)
        other = register_login(c, 'other@example.com')
        assert draft(c, other, ref).status_code == 404


def test_manual_homework_removes_only_its_occurrence_from_pending_courses(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        original = opened(c, h)
        event_ref = lesson(c)
        d = draft(c, h, event_ref).json()
        assert confirm(c, h, d).status_code == 200
        current = opened(c, h)
        assert all(o['course_id'] != event_ref['course_id'] for group in current['courses'] for o in group['occurrences'])
        # Existing forms must conflict rather than create duplicate homework.
        assert submit(c, h, original, [{'course_key': original['courses'][0]['key'], 'status': 'none', 'items': []}]).status_code == 409


def test_expired_form_requires_explicit_manual_submission(tmp_path, monkeypatch):
    current = clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        before = opened(c, h)
        current[0] = datetime.fromisoformat('2026-10-15T10:00:00+08:00')
        answers = [{'course_key': before['courses'][0]['key'], 'status': 'none', 'items': []}]
        assert submit(c, h, before, answers).status_code == 409
        body = {'revision': before['review']['revision'], 'manual': True, 'answers': answers}
        assert write(c, h, f"/api/after-class/{before['review']['id']}/submit", body).status_code == 200


def test_resolves_moved_lesson_using_original_identity(tmp_path, monkeypatch):
    clock(monkeypatch)
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        ref = lesson(c)
        assert write(c, h, '/api/calendar-exceptions', {
            'course_id': ref['course_id'], 'date': ref['original_date'],
            'starts_at': '2026-10-16T10:00:00+08:00', 'ends_at': '2026-10-16T11:00:00+08:00',
        }).status_code == 200
        response = draft(c, h, ref); assert response.status_code == 200, response.text
        assert confirm(c, h, response.json()).status_code == 200
        snapshot = c.get('/api/tasks').json()[0]['data']['course_occurrence_snapshot']
        assert snapshot['original_date'] == '2026-10-14'
        assert datetime.fromisoformat(snapshot['starts_at']).date().isoformat() == '2026-10-16'


def test_agent_creates_lesson_linked_draft_and_waits_for_confirmation(tmp_path, monkeypatch):
    import json
    from uuid import uuid4
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from tests.test_agent import ToolModel, wait_run

    clock(monkeypatch)
    class HomeworkModel(ToolModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            last = messages[-1]
            if isinstance(last, ToolMessage) and last.name == 'list_course_occurrences':
                event = json.loads(last.content)[0]
                call = {'name': 'create_assignment_draft', 'args': {
                    'title': '历史课程练习', 'estimated_minutes': 35,
                    'course_occurrence': {'course_id': event['course_id'], 'original_date': event['original_date']},
                }, 'id': str(uuid4()), 'type': 'tool_call'}
            elif isinstance(last, ToolMessage):
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='请校对作业草稿。'))])
            else:
                call = {'name': 'list_course_occurrences', 'args': {'start_date': '2026-10-14', 'end_date': '2026-10-14'}, 'id': str(uuid4()), 'type': 'tool_call'}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=[call]))])
    with make_client(tmp_path) as c:
        h = register_login(c); seed(c, h)
        c.app.state.agent_model_factory = HomeworkModel
        thread = write(c, h, '/api/agent/threads', {}).json()
        run = write(c, h, '/api/agent/runs', {'thread_id': thread['id'], 'message': '补记14日那节课的作业，预计35分钟'}).json()
        assert wait_run(c, run['id'])['data']['status'] == 'done'
        assert c.get('/api/tasks').json() == []
        d = c.get('/api/drafts').json()[0]
        assert d['data']['payload']['items'][0]['course_occurrence']['original_date'] == '2026-10-14'
        assert confirm(c, h, d).status_code == 200
        task = c.get('/api/tasks').json()[0]
        assert task['data']['course_occurrence']['original_date'] == '2026-10-14'
