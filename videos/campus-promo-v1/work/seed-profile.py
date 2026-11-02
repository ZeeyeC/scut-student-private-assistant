"""Seed fictional courses only after checking the running data identity."""
from pathlib import Path
import json, sys, uuid
import httpx

repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'backend'))
from app.launcher import desktop_config, service_identity
profile=Path(__file__).resolve().parent/'profile'
resources=Path.home()/'ProjectManagement/Demo2.9/课间桌宠.app/Contents/Resources/service/_internal'
expected=service_identity(desktop_config(profile,resources,project=False))
base='http://127.0.0.1:5173'
client=httpx.Client(base_url=base,trust_env=False,timeout=30)
health=client.get('/api/healthz').raise_for_status().json()
assert health['database_id']==expected['database_id'], 'Wrong data identity; refusing writes'
assert health['runtime_id']==json.loads((resources/'service-build.json').read_text())['runtime_id'], 'Wrong runtime; refusing writes'
csrf=client.get('/api/csrf').raise_for_status().json()['csrf_token']
headers={'Origin':base,'X-CSRF-Token':csrf}
client.post('/api/local/session',json={},headers=headers).raise_for_status()
def write(method,url,**kwargs):
    r=client.request(method,url,headers={**headers,'Idempotency-Key':str(uuid.uuid4())},**kwargs)
    if r.is_error:
        print(r.status_code,r.text[:1200]);r.raise_for_status()
    return r.json()
manifest=json.loads((repo/'videos/campus-promo-v1/materials/fictional-data.json').read_text())
settings=client.get('/api/settings').raise_for_status().json()
settings['data'].update(semester_name='虚构演示学期',week1_monday=manifest['semester_week1_monday'],week_count=18,campus_preset='wushan',periods={})
write('PUT','/api/settings',json={'revision':settings['revision'],'data':settings['data']})
courses=client.get('/api/courses').raise_for_status().json()
if not courses:
    draft=write('POST','/api/drafts/timetable',json={'semester_label':'虚构演示学期','courses':manifest['courses']})
    write('POST',f"/api/drafts/{draft['id']}/confirm",json={'revision':draft['revision']})
courses=client.get('/api/courses').raise_for_status().json()
assert len(courses)==3
pref=client.get('/api/after-class/preferences').raise_for_status().json()
write('PUT','/api/after-class/preferences',json={'revision':pref['revision'],'enabled':False,'delay_minutes':15})
sources=client.get('/api/knowledge/sources').raise_for_status().json()
if not sources:
    course=next(c for c in courses if c['data']['name']=='微积分')
    document=repo/'videos/campus-promo-v1/materials/微积分-导数应用练习.pdf'
    with document.open('rb') as f:
        write('POST','/api/knowledge/documents',files={'file':(document.name,f,'application/pdf')},data={'course_id':course['id']})
record={'isolated_identity_verified':True,'course_count':len(courses),'source_count':len(client.get('/api/knowledge/sources').json()),'model_configured':health['model_configured'],'vision_configured':health.get('vision_configured'),'seeded_by':'real application API; fictional fixtures only'}
(profile.parent/'profile-check.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False))
