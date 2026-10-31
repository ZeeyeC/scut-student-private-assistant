import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type { Resource } from './types';
import type { ScheduleEvent } from './schedule';
import { Button } from './components/ui/button';
import { DraftActions } from './Assignments';
import { constraintInput, constraintInstant } from './constraint-time';

const when = (e: Record<string, any> | null, timezone: string) => e
  ? `${(e.occupied_intervals ?? [e]).map((part: Record<string, any>)=>`${new Date(part.starts_at).toLocaleString('zh-CN',{timeZone:timezone})} – ${new Date(part.ends_at).toLocaleString('zh-CN',{timeZone:timezone})}`).join('；')}${e.location ? ` · ${e.location}` : ''}`
  : '本次不上课';

export function CourseChangeForm({event, timezone, onClose}:{event:ScheduleEvent;timezone:string;onClose:()=>void}) {
  const q=useQueryClient();
  const [action,setAction]=useState('move');
  const [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const [key,setKey]=useState(crypto.randomUUID());
  return <form aria-label="调整本次课程" className="card" onChange={()=>{setKey(crypto.randomUUID());setError('');}} onSubmit={async e=>{
    e.preventDefault(); if(busy)return;
    const f=new FormData(e.currentTarget);setBusy(true);setError('');
    try {
      await api('/drafts/course-change',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({
        course_id:event.course_id, original_date:event.original_date, action,
        reason:String(f.get('reason')),
        ...(action==='move' ? {starts_at:constraintInstant(String(f.get('start')),timezone),ends_at:constraintInstant(String(f.get('end')),timezone),location:String(f.get('location')),campus:String(f.get('campus')) || null} : {}),
      })});
      await q.invalidateQueries({queryKey:['drafts']}); onClose();
    } catch(e){setError(String(e));}finally{setBusy(false);}
  }}>
    <h3>{event.title} · 原课日期 {event.original_date}</h3>
    <p>调整原日期这门课的全部节次，其他周不变。新起止若改变，按填写的一个连续时段授课，不推算课间；仅换教室且起止不变时保留原分段。填写教师或教务通知依据，生成草稿后再确认。</p>
    <fieldset disabled={busy}>
      <label>调整方式<select value={action} onChange={e=>setAction(e.target.value)}><option value="move">调课或更换教室</option><option value="cancel">本次停课</option></select></label>
      {action==='move' && <div className="grid2">
        <label>新上课时间<input name="start" type="datetime-local" required defaultValue={constraintInput(event.occurrence_starts_at ?? event.starts_at,timezone)} /></label>
        <label>新下课时间<input name="end" type="datetime-local" required defaultValue={constraintInput(event.occurrence_ends_at ?? event.ends_at,timezone)} /></label>
        <label>新教室<input name="location" maxLength={200} defaultValue={event.location??''} /></label>
        <label>本次校区<input name="campus" maxLength={100} defaultValue={event.campus??''} placeholder="请按调课通知确认，未知可留空" /></label>
      </div>}
      <label>调整依据<textarea name="reason" required maxLength={1000} placeholder="例如：10月14日教师通知，本周课程改到周四晚上" /></label>
    </fieldset>
    {error && <p role="alert">{error}</p>}
    <Button disabled={busy}>{busy?'正在生成…':'预览课程调整'}</Button>{' '}
    <Button type="button" variant="outline" disabled={busy} onClick={onClose}>取消调整</Button>
  </form>;
}

export function CourseChangeReview({draft}:{draft:Resource}) {
  const [error,setError]=useState('');
  const p=draft.data.payload, review=draft.data.source.preview;
  // The preview records the exact timezone used by the server.
  const timezone=review.timezone ?? 'Asia/Shanghai';
  return <section className="card" aria-label="课程调整草稿">
    <p className="eyebrow">课程调整 · 尚未生效</p>
    <h2>{review.course.data.name} · {p.action==='cancel'?'本次停课':p.action==='restore'?'恢复原课':'本次调课'}</h2>
    <p>原课日期 {p.original_date} · 仅此一次</p>
    <p>依据：{p.reason}</p>
    <h3>调整前</h3><p>{when(review.before,timezone)}</p>
    <h3>确认后</h3><p>{when(review.after,timezone)}</p>
    {review.conflicts.length>0 && <div role="alert"><h3>新时间存在冲突，请核对</h3>{review.conflicts.map((e:ScheduleEvent)=><p key={e.id}>{e.title} · {when(e,timezone)}{e.locked?' · 已锁定':''}</p>)}</div>}
    {review.affected_plans.length>0 && <div><h3>需检查的学习安排</h3>{review.affected_plans.map((e:ScheduleEvent)=><p key={e.id}>{e.title} · {when(e,timezone)}{e.locked?' · 已锁定':''}</p>)}</div>}
    <p>{review.message}</p>
    <DraftActions draft={draft} payload={p} onError={setError} />
    {error && <p role="alert">{error}</p>}
  </section>;
}

export function CourseChangeHistory({timezone}:{timezone:string}) {
  const q=useQueryClient();
  const rows=useQuery({queryKey:['course-changes'],queryFn:()=>api<Resource[]>('/course-changes')});
  const history=useQuery({queryKey:['course-change-history'],queryFn:()=>api<Resource[]>('/course-change-history')});
  const courses=useQuery({queryKey:['courses'],queryFn:()=>api<Resource[]>('/courses')});
  const [busy,setBusy]=useState(''),[error,setError]=useState('');
  const [keys,setKeys]=useState<Record<string,string>>({});
  if(!rows.data?.length&&!rows.error)return null;
  return <section className="card" aria-label="已确认课程调整">
    <h2>已确认课程调整</h2>
    {rows.error && <p role="alert">{String(rows.error)}</p>}
    {rows.data?.map(row=><div className="step" key={row.id}>
      <h3>{courses.data?.find(c=>c.id===row.data.course_id)?.data.name ?? row.data.source?.original?.title ?? '课程'} · 原课日期 {row.data.date}</h3>
      <p>{row.data.retired_by_timetable?'已随旧课表停用，历史记录保留':row.data.active===false?'已恢复原课':row.data.cancelled?'本次已停课':row.data.starts_at ? `已调至 ${when(row.data,timezone)}` : '沿用原时间'}</p>
      <p>依据：{row.data.source?.reason ?? '旧版接口记录，未填写来源'}</p>
      {row.data.active!==false && <Button variant="outline" disabled={!!busy} onClick={async()=>{
        setBusy(row.id);setError('');
        const key=keys[row.id]??crypto.randomUUID();setKeys(k=>({...k,[row.id]:key}));
        try {
          await api('/drafts/course-change',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({course_id:row.data.course_id,original_date:row.data.date,action:'restore',reason:'用户请求撤销本次调整，恢复原课表'})});
          await q.invalidateQueries({queryKey:['drafts']});setKeys(k=>{const result={...k};delete result[row.id];return result;});
        }catch(e){setError(String(e));}finally{setBusy('');}
      }}>恢复原课（先预览）</Button>}
    </div>)}
    {history.error && <p role="alert">{String(history.error)}</p>}
    {!!history.data?.length && <details><summary>查看调整记录</summary>{[...history.data].reverse().map(r=>{
      const d=r.data.details, p=d.preview;
      return <div className="step" key={r.id}><h3>{p.course.data.name} · {d.action==='move'?'调课':d.action==='cancel'?'停课':'恢复原课'}</h3>
        <p>{new Date(r.data.occurred_at).toLocaleString('zh-CN',{timeZone:timezone})} · 原课日期 {p.original.original_date}</p>
        <p>依据：{d.after.data.source.reason}</p><p>调整前：{when(p.before,p.timezone)}</p><p>确认后：{when(p.after,p.timezone)}</p>
      </div>;
    })}</details>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
