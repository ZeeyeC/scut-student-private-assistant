import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import { Button } from './components/ui/button';
import type { components } from './generated-api';

type Report = components['schemas']['ReplanReport'];

export function Replanning() {
  const q = useQueryClient();
  const report = useQuery({queryKey:['replanning'], queryFn:()=>api<Report>('/replanning')});
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const p = report.data;
  return <section className="card" aria-label="日程变化检查">
    <h2>安排有变化？</h2>
    <p>检查未来 7 天，尽量保留原来的安排，只替换受影响的部分。锁定、已完成和已开始的安排保留，问题会单独提示；确认草稿后才保存。</p>
    <Button variant="outline" disabled={busy || report.isFetching} onClick={()=>report.refetch()}>检查日程变化</Button>{' '}
    <Button disabled={busy || report.isFetching || !p?.needs_changes || !!report.error} onClick={async()=>{
      setBusy(true); setError('');
      try {
        await api('/replan-drafts',{method:'POST',body:JSON.stringify({horizon_days:7})});
        await q.invalidateQueries({queryKey:['drafts']});
      } catch(e) { setError(String(e)); } finally { setBusy(false); }
    }}>{busy ? '正在生成…' : '生成重排草稿'}</Button>
    {report.isFetching && <p role="status">正在核对已有安排…</p>}
    {(error || report.error) && <p role="alert">{error || String(report.error)}</p>}
    {p && !report.error && <>
      <p>{p.needs_changes ? '有可调整的安排' : '没有需要替换或新增的安排'} · 保留 {p.retained_ids.length} 项 · 替换或移除 {p.removed.length} 项 · 新增 {p.added.length} 项 · 仍未排 {p.unallocated_minutes} 分钟</p>
      {p.removed.map(b=><p key={b.id}><strong>{b.title}</strong>：{b.reason}</p>)}
      {p.added.length>0 && <details><summary>查看建议的新安排</summary>{p.added.map(b=><p key={b.id}>{b.title} · {new Date(b.starts_at).toLocaleString('zh-CN', {timeZone:p.timezone})}–{new Date(b.ends_at).toLocaleTimeString('zh-CN', {timeZone:p.timezone})}</p>)}</details>}
      {p.warnings.map((w,i)=><p role="alert" key={i}>{w}</p>)}
    </>}
  </section>;
}
