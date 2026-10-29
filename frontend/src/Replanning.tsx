import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import { Button } from './components/ui/button';
import type { components } from './generated-api';
import type { Resource } from './types';

type Report = components['schemas']['ReplanReport'];

export function Replanning() {
  const q = useQueryClient();
  const report = useQuery({queryKey:['replanning'], queryFn:()=>api<Report>('/replanning')});
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const changes=useQuery({queryKey:['replanning-changes'],queryFn:async()=>{
    if(document.visibilityState==='hidden')return api<Resource|null>('/replanning/changes');
    return (await api<{notice:Resource|null}>('/replanning/changes',{method:'POST',body:JSON.stringify({app_active:true})})).notice;
  },refetchInterval:30000,refetchIntervalInBackground:false});
  const notice=changes.data;
  const consume=()=>changes.refetch();
  useEffect(()=>{
    const changed=()=>{if(document.visibilityState!=='hidden')void q.invalidateQueries({queryKey:['replanning-changes']});};
    document.addEventListener('visibilitychange',changed);
    window.addEventListener('focus',changed);
    return ()=>{document.removeEventListener('visibilitychange',changed);window.removeEventListener('focus',changed);};
  },[q]);
  const p = (notice?.data.state==='pending'?notice.data.report:report.data) as Report|undefined;
  return <section className="card" aria-label="日程变化检查">
    <h2>安排有变化？</h2>
    <p>检查未来 7 天，尽量保留原来的安排，只替换受影响的部分。锁定、已完成和已开始的安排保留，问题会单独提示；确认草稿后才保存。</p>
    <p>界面打开时及活跃期间每 30 秒合并检查变化；不发声、不自动改日程。</p>
    {notice&&<p role="status">变化建议：{({pending:'待校对',resolved:'已核对',dismissed:'已忽略本次结果',invalidated:'依据已变化，请重新检查',confirmed:'已确认'})[notice.data.state as string]}</p>}
    <Button variant="outline" disabled={busy || report.isFetching} onClick={()=>{void consume();void report.refetch();}}>检查日程变化</Button>{' '}
    <Button disabled={busy || report.isFetching || !p?.needs_changes || !!report.error} onClick={async()=>{
      setBusy(true); setError('');
      try {
        if(notice?.data.state==='pending')await api('/replanning/changes/draft',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({revision:notice.revision,source_revision:notice.data.source_revision})});
        else await api('/replan-drafts',{method:'POST',body:JSON.stringify({horizon_days:7})});
        await q.invalidateQueries({queryKey:['drafts']});
        await consume();
      } catch(e) { setError(String(e)); } finally { setBusy(false); }
    }}>{busy ? '正在生成…' : '生成重排草稿'}</Button>
    {notice?.data.state==='pending'&&<Button variant="outline" disabled={busy} onClick={async()=>{
      setBusy(true);setError('');try{
        q.setQueryData(['replanning-changes'],await api<Resource>('/replanning/changes/dismiss',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({revision:notice.revision,source_revision:notice.data.source_revision})}));
      }catch(e){setError(String(e));}finally{setBusy(false);}
    }}>忽略本次变化建议</Button>}
    {report.isFetching && <p role="status">正在核对已有安排…</p>}
    {(error || report.error || changes.error) && <p role="alert">{error || String(report.error || changes.error)}</p>}
    {p && !report.error && <>
      <p>{p.needs_changes ? '有可调整的安排' : '没有需要替换或新增的安排'} · 保留 {p.retained_ids.length} 项 · 替换或移除 {p.removed.length} 项 · 新增 {p.added.length} 项 · 仍未排 {p.unallocated_minutes} 分钟</p>
      {p.removed.map(b=><p key={b.id}><strong>{b.title}</strong>：{b.reason}</p>)}
      {p.added.length>0 && <details><summary>查看建议的新安排</summary>{p.added.map(b=><p key={b.id}>{b.title} · {new Date(b.starts_at).toLocaleString('zh-CN', {timeZone:p.timezone})}–{new Date(b.ends_at).toLocaleTimeString('zh-CN', {timeZone:p.timezone})}</p>)}</details>}
      {p.warnings.map((w,i)=><p role="alert" key={i}>{w}</p>)}
    </>}
  </section>;
}
