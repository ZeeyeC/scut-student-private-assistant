import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type { Resource } from './types';
import { Button } from './components/ui/button';
import { PlanReview } from './Today';
import { visibleDrafts } from './drafts';

export function SmartSchedule() {
  const q = useQueryClient();
  const drafts = useQuery({queryKey:['drafts'],queryFn:()=>api<Resource[]>('/drafts')});
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  return <section aria-label="智能安排">
    <div className="card">
      <h2>智能安排任务</h2>
      <p>课表中的课程是固定占用。根据待办步骤、耗时、截止时间和学习窗口，避开课程、固定事项及锁定安排，生成未来 7 天的日程建议。排不下的任务会说明原因；确认后才保存。</p>
      <Button disabled={busy} onClick={async()=>{
        setBusy(true);setError('');
        try { await api('/plan-drafts',{method:'POST',body:JSON.stringify({horizon_days:7})}); await q.invalidateQueries({queryKey:['drafts']}); }
        catch(e){setError(String(e));}finally{setBusy(false);}
      }}>{busy ? '正在计算…' : '智能安排未来 7 天'}</Button>
      {error && <p role="alert">{error}</p>}
    </div>
    {visibleDrafts(drafts.data).filter(d=>d.data.draft_kind==='plan').map(d=><PlanReview draft={d} key={d.id+':'+d.revision}/>)}
  </section>;
}
