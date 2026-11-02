"""Library inventory and classification: real owned sources and guarded writes."""
from pathlib import Path
from uuid import uuid4
import pytest
from app.db import Resource
from tests.test_foundation import make_client,register_login
from tests.test_knowledge import upload


def seed(c,kind,data,owner=None,rid=None):
    owner=owner or c.get('/api/me').json()['id'];rid=rid or str(uuid4())
    async def write():
        async with c.app.state.sessions() as db:
            db.add(Resource(id=rid,owner_id=owner,kind=kind,data=data));await db.commit()
    c.portal.call(write);return rid


def patch(c,path,**kwargs):
    kwargs['headers']={'Idempotency-Key':str(uuid4()),**kwargs.get('headers',{})}
    return c.patch(path,**kwargs)


def change_data(c,rid,change):
    async def write():
        async with c.app.state.sessions() as db:
            r=await db.get(Resource,rid);r.data=change(dict(r.data));await db.commit()
    c.portal.call(write)


def test_inventory_all_sources_summary_filter_sort_and_missing_metadata(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c)
        a=upload(c,h,name='B讲义.md',raw=b'content B').json()['id']
        b=upload(c,h,name='A讲义.md',raw=b'content A').json()['id']
        course=seed(c,'course',{'name':'高等数学'})
        change_data(c,a,lambda d:{**d,'course_id':course})
        change_data(c,b,lambda d:{k:v for k,v in d.items() if k not in {'size_bytes','created_at'}})
        r=c.get('/api/knowledge/library?sort=name&limit=1');assert r.status_code==200,r.text
        data=r.json();assert data['total']==data['all_count']==2
        assert len(data['items'])==1 and data['items'][0]['id']==b
        info=data['items'][0]['data'];assert 'chunks' not in info and 'storage_name' not in info
        assert info['size_bytes']==len(b'content A') and info['created_at'] is None
        assert data['courses']==[{'id':course,'name':'高等数学','count':1,'missing':False}]
        assert data['unclassified_count']==1
        assert c.get('/api/knowledge/library?sort=name&offset=1&limit=1').json()['items'][0]['id']==a
        assert c.get('/api/knowledge/library',params={'course_id':course}).json()['items'][0]['id']==a
        assert c.get('/api/knowledge/library?unclassified=true').json()['items'][0]['id']==b
        assert c.get('/api/knowledge/library',params={'query':'B讲义'}).json()['total']==1
        for query in ['limit=101','offset=-1','sort=invalid','course_id=x&unclassified=true']:
            assert c.get('/api/knowledge/library?'+query).status_code==422


def test_course_changes_are_owned_revisioned_idempotent_and_do_not_copy_source_text(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c);sid=upload(c,h).json()['id'];course=seed(c,'course',{'name':'数学'})
        before=c.get('/api/knowledge/sources/'+sid).json()
        old_epoch=c.get('/api/memories').json()['settings']['data']['privacy_epoch']
        body={'revision':before['revision'],'course_id':course}
        result=patch(c,'/api/knowledge/sources/'+sid+'/course',json=body,headers={**h,'Idempotency-Key':'classify'})
        assert result.status_code==200,result.text
        assert patch(c,'/api/knowledge/sources/'+sid+'/course',json=body,headers={**h,'Idempotency-Key':'classify'}).json()==result.json()
        after=c.get('/api/knowledge/sources/'+sid).json()
        assert after['revision']==before['revision']+1 and after['data']['course_id']==course
        assert after['data']['chunks']==before['data']['chunks'] and after['data']['storage_name']==before['data']['storage_name']
        assert c.get('/api/memories').json()['settings']['data']['privacy_epoch']>old_epoch
        assert patch(c,'/api/knowledge/sources/'+sid+'/course',json=body,headers={**h,'Idempotency-Key':'stale'}).status_code==409
        cleared=patch(c,'/api/knowledge/sources/'+sid+'/course',json={'revision':after['revision'],'course_id':None},headers={**h,'Idempotency-Key':'clear'})
        assert cleared.status_code==200
        assert c.get('/api/knowledge/library?unclassified=true').json()['total']==1
        assert patch(c,'/api/knowledge/sources/'+sid+'/course',json={'revision':cleared.json()['revision'],'course_id':'not-owned'},headers=h).status_code==404


def test_deleted_and_duplicate_named_courses_remain_distinct_and_missing_original_is_unknown(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c);first=seed(c,'course',{'name':'重名课程'});second=seed(c,'course',{'name':'重名课程'})
        for name,course in [('one.md',first),('two.md',second),('three.md',str(uuid4()))]:
            sid=upload(c,h,name).json()['id'];change_data(c,sid,lambda d:{**d,'course_id':course})
        d=c.get('/api/knowledge/library').json();assert len(d['courses'])==3
        assert len([r for r in d['courses'] if r['name']=='重名课程'])==2
        assert sum(r['missing'] for r in d['courses'])==1
        source=d['items'][0]
        async def remove_original():
            async with c.app.state.sessions() as db:
                r=await db.get(Resource,source['id']);r.data={**r.data,'size_bytes':None};await db.commit()
        c.portal.call(remove_original)
        from app.knowledge import storage_path
        raw=c.get('/api/knowledge/sources/'+source['id']).json();storage_path(c.app.state.config,c.get('/api/me').json()['id'],raw['data']['storage_name']).unlink()
        found=next(r for r in c.get('/api/knowledge/library').json()['items'] if r['id']==source['id'])
        assert found['data']['size_bytes'] is None


def test_foreign_user_cannot_list_reclassify_or_bind_another_users_course(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c);sid=upload(c,h).json()['id'];course=seed(c,'course',{'name':'私人课程'})
        c.post('/api/auth/logout',headers=h);other=register_login(c,'other@example.com')
        own=upload(c,other).json()['id']
        assert c.get('/api/knowledge/library').json()['all_count']==1
        assert c.get('/api/knowledge/library',params={'course_id':course}).status_code==404
        assert patch(c,'/api/knowledge/sources/'+sid+'/course',json={'revision':1,'course_id':None},headers=other).status_code==404
        assert patch(c,'/api/knowledge/sources/'+own+'/course',json={'revision':1,'course_id':course},headers=other).status_code==404
        assert c.get('/api/knowledge/library').json()['courses']==[]


def test_classification_rejects_busy_assistant_and_invalid_input(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c);sid=upload(c,h).json()['id'];course=seed(c,'course',{'name':'课程'})
        for data in [{'revision':True,'course_id':None},{'revision':1},{'revision':1,'course_id':None,'chunks':[]}]:
            assert patch(c,'/api/knowledge/sources/'+sid+'/course',json=data,headers=h).status_code==422
        seed(c,'agent_run',{'status':'running'})
        assert patch(c,'/api/knowledge/sources/'+sid+'/course',json={'revision':1,'course_id':course},headers=h).status_code==409
        assert c.get('/api/knowledge/sources/'+sid).json()['data']['course_id'] is None


def test_web_sources_are_listed_without_original_file_size_or_text(tmp_path,monkeypatch):
    from app import web_research
    async def read(url):return {'url':url,'title':'公开课程网页','text':'第一段\n\n第二段'}
    monkeypatch.setattr(web_research,'read_webpage',read)
    with make_client(tmp_path) as c:
        h=register_login(c);r=c.post('/api/knowledge/web',json={'url':'https://example.com/course'},headers={**h,'Idempotency-Key':'web'})
        assert r.status_code==200,r.text
        data=c.get('/api/knowledge/library').json();assert data['all_count']==1
        item=data['items'][0]['data'];assert item['format']=='web' and item['source_type']=='web'
        assert item['size_bytes'] is None and item['chunk_count']==2 and 'chunks' not in item


def test_unclassified_text_search_cannot_return_classified_sources(tmp_path):
    with make_client(tmp_path) as c:
        h=register_login(c)
        course=seed(c,'course',{'name':'高等数学'})
        first=upload(c,h,name='已分类.md',raw=b'algebraexclusive').json()['id']
        upload(c,h,name='未分类.md',raw=b'neutralexclusive')
        change_data(c,first,lambda d:{**d,'course_id':course})
        response=c.post('/api/knowledge/search',headers=h,json={'query':'algebraexclusive','unclassified':True})
        assert response.status_code==200,response.text
        assert response.json()['items']==[]
        response=c.post('/api/knowledge/search',headers=h,json={'query':'neutralexclusive','unclassified':True})
        assert len(response.json()['items'])==1
        assert c.post('/api/knowledge/search',headers=h,json={'query':'unique','course_id':course,'unclassified':True}).status_code==422
