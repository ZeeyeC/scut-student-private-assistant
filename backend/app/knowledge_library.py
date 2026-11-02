"""Owned source inventory; classification edits preserve canonical text/originals."""
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from app import knowledge,memories,store


def source_size(config,owner,data):
    size=data.get('size_bytes')
    if type(size) is int and size>=0:return size
    if data.get('format')=='web' or not data.get('storage_name'):return None
    try:
        path=knowledge.storage_path(config,owner,data['storage_name'])
        return path.stat().st_size if path.is_file() else None
    except (HTTPException,OSError,ValueError,TypeError):
        return None


def summary(config,owner,r,courses):
    d=r.data;cid=d.get('course_id');course=courses.get(cid)
    return {'id':r.id,'kind':'knowledge_source','revision':r.revision,'data':{
        'filename':d.get('filename',d.get('title','资料')),'title':d.get('title',d.get('filename','资料')),
        'format':d.get('format','txt'),'source_type':d.get('source_type','web' if d.get('format')=='web' else 'document'),
        'course_id':cid,'course_name':course.data.get('name','未命名课程') if course else None,
        'course_missing':bool(cid and not course),'size_bytes':source_size(config,owner,d),
        'created_at':d.get('created_at'),'url':d.get('url'),'chunk_count':len(d.get('chunks',[])),
        'truncated':bool(d.get('truncated'))}}


async def inventory(db,owner,config,*,course_id=None,unclassified=False,query='',sort='newest',offset=0,limit=50):
    if course_id and unclassified:raise HTTPException(422,'不能同时选择课程与未分类')
    resources=await store.rows(db,owner,'knowledge_source')
    courses={r.id:r for r in await store.rows(db,owner,'course')}
    # Deleted course categories remain selectable only if actually referenced by
    # this owner's saved sources. Other users' course IDs reveal no existence.
    referenced={r.data.get('course_id') for r in resources if r.data.get('course_id')}
    if course_id and course_id not in courses and course_id not in referenced:raise HTTPException(404,'课程不存在')
    counts={}
    for r in resources:
        cid=r.data.get('course_id')
        if cid:counts[cid]=counts.get(cid,0)+1
    categories=[{'id':cid,'name':courses[cid].data.get('name','未命名课程') if cid in courses else '原课程已移除',
                 'count':count,'missing':cid not in courses} for cid,count in counts.items()]
    categories.sort(key=lambda c:(c['missing'],c['name'],c['id']))
    q=query.strip().casefold()
    filtered=[r for r in resources if (not course_id or r.data.get('course_id')==course_id)
              and (not unclassified or not r.data.get('course_id'))
              and (not q or q in str(r.data.get('filename','')).casefold() or q in str(r.data.get('title','')).casefold())]
    if sort=='name':filtered.sort(key=lambda r:(str(r.data.get('filename',r.data.get('title',''))).casefold(),r.id))
    else:
        def date_key(r):
            try:
                value=datetime.fromisoformat(r.data.get('created_at') or '')
                return value.timestamp() if value.tzinfo else float('-inf')
            except (ValueError,TypeError,OverflowError):return float('-inf')
        filtered.sort(key=lambda r:(date_key(r),r.id),reverse=True)
    return {'items':[summary(config,owner,r,courses) for r in filtered[offset:offset+limit]],
            'total':len(filtered),'all_count':len(resources),'courses':categories,
            'unclassified_count':len(resources)-sum(counts.values())}


async def classify(db,owner,rid,body,key):
    payload=body.model_dump(mode='json')
    async def op():
        r=await store.owned(db,owner,rid,'knowledge_source')
        store.revision(r,body.revision)
        await memories.idle(db,owner)
        await knowledge.check_course(db,owner,body.course_id)
        if r.data.get('course_id')!=body.course_id:
            r.data={**r.data,'course_id':body.course_id};r.revision+=1
            await memories.epoch(db,owner)
            await db.flush()
        return {'id':r.id,'revision':r.revision}
    # Ownership is checked even for receipt replay, including a deleted source.
    await store.owned(db,owner,rid,'knowledge_source')
    return await store.mutate(db,owner,'knowledge-classification:'+rid,key,payload,op)
