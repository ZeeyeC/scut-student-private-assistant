import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type { Resource } from './types';
import { Button } from './components/ui/button';
import { PlanReview } from './Today';
import { visibleDrafts } from './drafts';
import { SchedulingConstraints } from './SchedulingConstraints';
import { PlanningCapacity } from './PlanningCapacity';
import { Replanning } from './Replanning';
import { PlanningWorkbench } from './PlanningWorkbench';
import { EventReview } from './EventReview';

export function SmartSchedule() {
  const q = useQueryClient();
  const drafts = useQuery({queryKey:['drafts'],queryFn:()=>api<Resource[]>('/drafts')});
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  return <section aria-label="智能安排">
    <SchedulingConstraints />
    <PlanningCapacity />
    <Replanning />
    <PlanningWorkbench />
    <div className="card">
      <h2>智能安排任务</h2>
      <p>根据待办步骤、耗时、截止时间和学习窗口，避开课程、固定事项、已确认禁排及锁定安排。可只安排今天剩余时间，也可规划未来 7 天。排不下的任务会说明原因；确认后才保存。</p>
      <Button disabled={busy} onClick={async()=>{
        setBusy(true);setError('');
        try { await api('/plan-drafts',{method:'POST',body:JSON.stringify({scope:'today'})}); await q.invalidateQueries({queryKey:['drafts']}); }
        catch(e){setError(String(e));}finally{setBusy(false);}
      }}>{busy ? '正在计算…' : '一键生成当日日程'}</Button>{' '}
      <Button disabled={busy} onClick={async()=>{
        setBusy(true);setError('');
        try { await api('/plan-drafts',{method:'POST',body:JSON.stringify({horizon_days:7})}); await q.invalidateQueries({queryKey:['drafts']}); }
        catch(e){setError(String(e));}finally{setBusy(false);}
      }}>{busy ? '正在计算…' : '智能安排未来 7 天'}</Button>
      {error && <p role="alert">{error}</p>}
    </div>
    {visibleDrafts(drafts.data).filter(d=>d.data.draft_kind==='calendar_event' && d.data.source?.routine_candidate_id).map(d=><EventReview draft={d} key={d.id+':'+d.revision}/>)}
    {visibleDrafts(drafts.data).filter(d=>d.data.draft_kind==='plan').map(d=><PlanReview draft={d} key={d.id+':'+d.revision}/>)}
  </section>;
}
