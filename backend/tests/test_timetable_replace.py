from tests.test_foundation import make_client, register_login
from tests.test_scheduling_constraints import write, confirm
from tests.test_conflicts import preview, timetable


def edited(c, h, d, mode):
    payload = {**d['data']['payload'], 'save_mode': mode}
    r = write(c, h, f"/drafts/{d['id']}", {'revision': d['revision'], 'payload': payload}, 'PUT')
    assert r.status_code == 200, r.text
    return r.json()


def checked_confirm(c, h, d, report=None, key=None):
    report = report or preview(c, h, d)
    return write(c, h, f"/drafts/{d['id']}/confirm", {'revision': d['revision'], 'conflict_token': report['conflict_token']}, key=key)


def test_empty_timetable_new_preview_allows_settings_updated_after_capture(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c); d = timetable(c, h)
        s = c.get('/api/settings').json(); s['data']['week_count'] = 25
        assert write(c, h, '/settings', s, 'PUT').status_code == 200
        assert c.get('/api/courses').json() == []
        assert confirm(c, h, d).status_code == 409  # old clients retain guard
        r = checked_confirm(c, h, d)
        assert r.status_code == 200, r.text
        assert len(c.get('/api/courses').json()) == 1


def test_replace_preview_and_commit_remove_only_missing_courses(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        old = timetable(c, h, source_key='old', name='旧课程'); assert confirm(c, h, old).status_code == 200
        task = write(c, h, '/drafts/assignment', {'items':[{'title':'保留任务','due_at':'2026-10-14T18:00:00+08:00'}]}).json()
        assert confirm(c, h, task).status_code == 200
        fixed = write(c,h,'/fixed-events',{'title':'保留事项','starts_at':'2026-10-14T17:00:00+08:00','ends_at':'2026-10-14T18:00:00+08:00'})
        assert fixed.status_code == 200, fixed.text
        before_tasks = c.get('/api/tasks').json(); before_fixed = c.get('/api/fixed-events').json()
        d = edited(c,h,timetable(c,h), 'replace'); report = preview(c,h,d)
        assert report['replacement']['removed_count'] == 1
        assert [x['data']['source_key'] for x in c.get('/api/courses').json()] == ['old']
        r = checked_confirm(c,h,d,report,key='replace-once'); assert r.status_code == 200, r.text
        assert len(r.json()['removed_course_ids']) == 1
        assert checked_confirm(c,h,d,report,key='replace-once').json() == r.json()
        assert [x['data']['source_key'] for x in c.get('/api/courses').json()] == ['second']
        assert c.get('/api/tasks').json() == before_tasks
        assert c.get('/api/fixed-events').json() == before_fixed


def test_replace_requires_preview_and_rejects_empty_capture(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c); d=edited(c,h,timetable(c,h),'replace')
        assert confirm(c,h,d).status_code == 422
        payload={**d['data']['payload'],'courses':[]}
        assert write(c,h,f"/drafts/{d['id']}",{'revision':d['revision'],'payload':payload},'PUT').status_code == 422


def test_preview_after_concurrent_change_must_be_repeated_and_merge_keeps_old(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c); old=timetable(c,h,source_key='old'); assert confirm(c,h,old).status_code==200
        d=edited(c,h,timetable(c,h),'replace'); report=preview(c,h,d)
        s=c.get('/api/settings').json(); s['data']['week_count']=25
        assert write(c,h,'/settings',s,'PUT').status_code==200
        assert checked_confirm(c,h,d,report).status_code==409
        assert len(c.get('/api/courses').json())==1
        d=edited(c,h,d,'merge'); assert checked_confirm(c,h,d).status_code==200
        assert len(c.get('/api/courses').json())==2


def test_replace_rechecks_new_courses_and_reuses_same_source_id(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c); old=timetable(c,h,source_key='same',name='旧名称')
        original=confirm(c,h,old).json()['saved_ids'][0]
        d=edited(c,h,timetable(c,h,source_key='same',name='校对名称'),'replace'); report=preview(c,h,d)
        other=timetable(c,h,source_key='concurrent'); assert confirm(c,h,other).status_code==200
        assert checked_confirm(c,h,d,report).status_code==409
        assert len(c.get('/api/courses').json())==2
        fresh=preview(c,h,d); assert fresh['replacement']['removed_count']==1
        r=checked_confirm(c,h,d,fresh); assert r.status_code==200, r.text
        assert r.json()['saved_ids']==[original]
        assert [x['data']['name'] for x in c.get('/api/courses').json()]==['校对名称']


def test_expired_school_capture_is_not_kept_as_an_actionable_draft(tmp_path):
    import sqlite3,json
    from tests.test_browser_import import configured_client
    with configured_client(tmp_path) as c:
        h=register_login(c); b=write(c,h,'/browser-imports',{'school_id':'scut'}).json()
        for kind in ['opened','waiting_timetable','extracting']:
            b=write(c,h,f"/browser-imports/{b['id']}/events",{'event_id':kind,'kind':kind,'revision':b['revision']}).json()
        r=write(c,h,f"/browser-imports/{b['id']}/capture",{'revision':b['revision'],'adapter_version':'test-fixture-v1','school_origin':'https://fixture.scut.edu.cn','semester_label':'合成学期','fragments':['<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th></tr><tr><td>过期草稿</td><td>1</td><td>1-8</td><td>1</td></tr></table>']})
        assert r.status_code==200,r.text
        with sqlite3.connect(tmp_path/'test.db') as db:
            data=json.loads(db.execute('select data from resources where id=?',(b['id'],)).fetchone()[0]);data['expires_at']='2000-01-01T00:00:00+00:00'
            db.execute('update resources set data=? where id=?',(json.dumps(data),b['id']))
        assert c.get('/api/browser-imports').json()[-1]['data']['status']=='expired'
        assert c.get('/api/drafts').json()==[]


def test_replacement_retires_old_adjustments_and_preserves_task_course_context(tmp_path):
    from tests.test_course_changes import change
    from tests.test_semester_calendar import rule
    with make_client(tmp_path) as c:
        h=register_login(c); s=c.get('/api/settings').json()
        s['data'].update(week1_monday='2026-10-12',periods={'2':{'start':'09:00','end':'10:00'}})
        assert write(c,h,'/settings',s,'PUT').status_code==200
        old=timetable(c,h,source_key='retired',name='历史课程',weeks=[1,2]); cid=confirm(c,h,old).json()['saved_ids'][0]
        task=write(c,h,'/drafts/assignment',{'items':[{'title':'保留学习任务','course_id':cid,'due_at':'2026-10-14T18:00:00+08:00'}]}).json()
        tid=confirm(c,h,task).json()['saved_ids'][0]
        cancelled=change(c,h,cid,'cancel').json(); assert confirm(c,h,cancelled).status_code==200
        batch=write(c,h,'/drafts/semester-calendar',rule(course_ids=[cid],start_date='2026-10-21',end_date='2026-10-21')).json()
        assert confirm(c,h,batch).status_code==200
        pending=change(c,h,cid,'restore').json()
        d=edited(c,h,timetable(c,h),'replace'); assert checked_confirm(c,h,d).status_code==200
        assert all(row['data']['active'] is False and row['data']['retired_by_timetable']==d['id'] for row in c.get('/api/course-changes').json())
        assert c.get(f"/api/drafts/{pending['id']}").json()['data']['status']=='superseded'
        saved_task=c.get(f'/api/tasks/{tid}').json()
        assert saved_task['data']['title']=='保留学习任务' and saved_task['data']['status']=='open'
        assert saved_task['data']['course_id'] is None
        assert saved_task['data']['course_snapshot']=={'id':cid,'name':'历史课程'}
        batches=c.get('/api/semester-calendars').json()
        assert batches[0]['data']['retired_by_timetable']==d['id']
        r=write(c,h,'/drafts/semester-calendar',{'operation':'undo','batch_id':batches[0]['id'],'reason':'尝试撤销旧批次'})
        assert r.status_code==422 and '覆盖' in r.json()['detail']
