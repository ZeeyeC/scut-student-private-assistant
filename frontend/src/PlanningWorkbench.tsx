import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type { components } from './generated-api';
import { Button } from './components/ui/button';
type Options = components['schemas']['Options'];
type Risks = components['schemas']['Risks'];
type RoutineRequest = components['schemas']['RoutineRequest'];
type Preview = components['schemas']['RoutinePreview'];

export function PlanningWorkbench() {
  const q=useQueryClient();
  const options=useQuery({queryKey:['planning-options'],queryFn:()=>api<Options>('/planning-options')});
  const risks=useQuery({queryKey:['planning-risks'],queryFn:()=>api<Risks>('/planning-risks')});
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [name,setName]=useState(''),[start,setStart]=useState(''),[end,setEnd]=useState('');
  const [prepare,setPrepare]=useState(''),[review,setReview]=useState(''),[commute,setCommute]=useState(false),[confirmed,setConfirmed]=useState(false);
  const [preview,setPreview]=useState<Preview|null>(null),[request,setRequest]=useState<RoutineRequest|null>(null);
  const act=async(action:()=>Promise<void>)=>{setBusy(true);setError('');try{await action();}catch(e){setError(String(e));}finally{setBusy(false);}};
  return <section className="card" aria-label="规划方案与日常候选">
    <h2>比较安排，再做决定</h2>
    <p>按截止、依赖、学习窗口和每日上限计算；软偏好可让步，课程与硬禁排不可突破。选择后先生成草稿，确认后才保存。</p>
    <Button variant="outline" disabled={busy} onClick={()=>{void options.refetch();void risks.refetch();}}>刷新方案与风险</Button>
    {(options.error||risks.error||error)&&<p role="alert">{error||String(options.error||risks.error)}</p>}
    {options.data&&<div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,260px),1fr))',gap:12}}>
      {options.data.options.map(o=><article className="step" key={o.id} aria-label={o.title}>
        <h3>{o.title}</h3><p>新排 {o.proposed_minutes} 分钟 · 未排 {o.unallocated_minutes} 分钟 · 偏好内 {o.preferred_minutes} 分钟</p>
        {o.explanation.map((s,i)=><p key={i}>{s}</p>)}
        <details><summary>查看时间安排</summary>{o.blocks.map(b=><p key={b.id}>{b.title} · {new Date(b.starts_at).toLocaleString('zh-CN',{timeZone:options.data?.timezone})}</p>)}</details>
        <Button disabled={busy||options.isFetching} onClick={()=>void act(async()=>{
          await api('/plan-drafts',{method:'POST',body:JSON.stringify({horizon_days:7,strategy:o.id,expected_source_revision:options.data!.source_revision})});
          await q.invalidateQueries({queryKey:['drafts']});
        })}>选择{o.title}</Button>
      </article>)}
    </div>}
    {risks.data&&<div aria-label="规划风险"><h3>时间与截止风险</h3>
      <p>容量上限 {risks.data.capacity_upper_bound_minutes} 分钟 · 待分配 {risks.data.required_minutes} 分钟 · 未排 {risks.data.unallocated_minutes} 分钟 · 耗时未知 {risks.data.unknown_estimate_count} 项</p>
      {!risks.data.risks.length&&<p>本次没有发现未排工作的风险。</p>}
      {risks.data.risks.map((r,i)=><p key={i}><strong>{r.title}</strong>：{r.remaining_minutes==null?'耗时未知':`${r.remaining_minutes} 分钟`} · {r.reason}</p>)}
    </div>}
    <h3>作息、课前准备与复习候选</h3>
    <p>填写你明确希望的时间或时长；留空表示本次不生成，不推测你的作息。可预览未来 7 天，忽略的同一候选不会重新建议。</p>
    <form onSubmit={e=>{e.preventDefault();void act(async()=>{
      if((start||end||name)&&!(start&&end&&name.trim()))throw new Error('作息需要同时填写名称、开始及结束时间');
      const body:RoutineRequest={confirmed:true,horizon_days:7,daily_windows:start&&end?[{title:name.trim(),start,end,weekdays:[1,2,3,4,5,6,7]}]:[],preparation_minutes:prepare?Number(prepare):0,review_minutes:review?Number(review):0,include_campus_transfer:commute};
      const result=await api<Preview>('/daily-routine-preview',{method:'POST',body:JSON.stringify(body)});setRequest(body);setPreview(result);
    });}}>
      <label>作息名称（可留空）<input value={name} maxLength={100} onChange={e=>setName(e.target.value)}/></label>
      <div className="grid2"><label>作息开始<input type="time" value={start} onChange={e=>setStart(e.target.value)}/></label><label>作息结束<input type="time" value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
      <div className="grid2"><label>课前准备分钟（可留空）<input type="number" min="0" max="180" value={prepare} onChange={e=>setPrepare(e.target.value)}/></label><label>课后复习分钟（可留空）<input type="number" min="0" max="180" value={review} onChange={e=>setReview(e.target.value)}/></label></div>
      <label className="check"><input type="checkbox" checked={commute} onChange={e=>setCommute(e.target.checked)}/>使用已确认的跨校区转移时长</label>
      <label className="check"><input type="checkbox" required checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>上述规则由我明确指定，仅生成待确认候选</label>
      <Button disabled={busy||!confirmed}>预览日常候选</Button>
    </form>
    {preview&&<div aria-label="日常候选列表">
      {preview.warnings.map((w,i)=><p key={i}>{w}</p>)}
      {preview.candidates.map(c=><article className="step" key={c.id}>
        <h4>{c.title}</h4><p>{new Date(c.starts_at).toLocaleString('zh-CN',{timeZone:preview.timezone})}–{new Date(c.ends_at).toLocaleTimeString('zh-CN',{timeZone:preview.timezone})}</p>
        {c.dismissed?<p>已忽略</p>:c.conflicts.map((x,i)=><p key={i}>{x}</p>)}
        <Button disabled={busy||!c.can_add} onClick={()=>void act(async()=>{
          await api('/daily-routine-drafts',{method:'POST',body:JSON.stringify({candidate_id:c.id,expected_source_revision:preview.source_revision,request})});await q.invalidateQueries({queryKey:['drafts']});
        })}>校对此候选</Button>{' '}
        <Button variant="outline" disabled={busy||c.dismissed} onClick={()=>void act(async()=>{
          await api('/daily-routine-dismiss',{method:'POST',body:JSON.stringify({candidate_id:c.id,expected_source_revision:preview.source_revision,request})});
          setPreview(await api<Preview>('/daily-routine-preview',{method:'POST',body:JSON.stringify(request)}));
        })}>忽略此候选</Button>
      </article>)}
    </div>}
  </section>;
}
