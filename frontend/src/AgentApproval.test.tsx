import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {describe, expect, it} from 'vitest';
import type {Resource} from './types';

const approval:Resource = {id:'approval-1',kind:'approval',revision:2,data:{run_id:'run-1',expires_at:'2099-01-01T00:00:00Z',decision:null,actions:[{name:'commit_import',args:{draft_id:'draft-1',revision:3}}]}};
const calendar:Resource = {id:'draft-1',kind:'draft',revision:3,data:{draft_kind:'calendar_event',status:'pending',payload:{title:'周三讨论',starts_at:'2026-11-04T14:00:00+08:00',ends_at:'2026-11-04T17:00:00+08:00'}}};
const report = {issues:[],conflict_count:0,pending_count:0,complete:true,conflict_token:'token-current',timezone:'Asia/Shanghai',configuration_warnings:[]};

async function render(draft:Resource|undefined, conflict:unknown=report, failed=false) {
  const {AgentApproval} = await import('./AgentApproval');
  const q=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}});
  q.setQueryData(['approval','approval-1'], approval);
  q.setQueryData(['settings'], {id:'settings',kind:'settings',revision:1,data:{timezone:'Asia/Shanghai'}});
  if(draft) q.setQueryData(['approval-draft','draft-1'],draft);
  if(conflict) q.setQueryData(['approval-conflict','approval-1','draft-1',3],conflict);
  if(failed) q.getQueryCache().find({queryKey:['approval-conflict','approval-1','draft-1',3]})?.setState({status:'error',error:new Error('预览失败')});
  const html=renderToStaticMarkup(createElement(QueryClientProvider,{client:q},createElement(AgentApproval,{id:'approval-1',runId:'run-1',onResume:()=>{}})));
  q.clear();
  return html;
}

function approveTag(html:string) {return html.match(/<button[^>]*>批准并执行<\/button>/)?.[0] || '';}

it('blocks conflict fact batches before any request and keeps rejection available',async()=>{
  const {approvalOperation}=await import('./AgentApproval');
  const batch={...approval,data:{...approval.data,actions:[...approval.data.actions,{name:'set_task_status',args:{task_id:'task-1',revision:1,status:'completed'}}]}};
  const evidence=[{action:batch.data.actions[0],resource:calendar,conflict:report},{action:batch.data.actions[1],resource:{id:'task-1',kind:'task',revision:1,data:{title:'另一项任务'}}}];
  expect(()=>approvalOperation(batch,'run-1','approve',evidence,{})).toThrow('逐项');
  expect(approvalOperation(batch,'run-1','reject',[],{}).body.decision).toBe('reject');
});

describe('agent approval checks the visible current content',()=>{
  it('requires real conflict preview and matching draft revision; rejection remains available',async()=>{
    const html=await render(calendar);
    expect(html).toContain('周三讨论');
    expect(html).toContain('冲突检查：0 项冲突');
    expect(approveTag(html)).not.toContain(' disabled=');
    const stale=await render({...calendar,revision:4});
    expect(approveTag(stale)).toContain(' disabled=');
    expect(stale).toContain('版本已变化');
    expect(stale.match(/<button[^>]*>拒绝<\/button>/)?.[0]).not.toContain(' disabled=');
    const missing=await render(undefined);
    expect(approveTag(missing)).toContain(' disabled=');
  });
  it('requires acknowledgement for conflict and unknown reports and blocks failed reports',async()=>{
    const html=await render(calendar,{...report,complete:false,pending_count:1});
    expect(html).toContain('type="checkbox"');
    expect(approveTag(html)).toContain(' disabled=');
    const failed=await render(calendar,report,true);
    expect(failed).toContain('预览失败');
    expect(approveTag(failed)).toContain(' disabled=');
  });
});

it('captures current tokens and acknowledgement, rejects stale checks, and reuses the exact lost-response operation',async()=>{
  const state=await import('./AgentApproval');
  const evidence=[{action:approval.data.actions[0],resource:calendar,conflict:{...report,conflict_count:1}}];
  expect(()=>state.approvalOperation(approval,'run-1','approve',evidence,{})).toThrow();
  const op=state.approvalOperation(approval,'run-1','approve',evidence,{'draft-1':'token-current'});
  expect(op.body).toEqual({approval_id:'approval-1',revision:2,decision:'approve',conflict_tokens:{'draft-1':'token-current'},conflict_acknowledged:['draft-1']});
  expect(op.path).toBe('/agent/runs/run-1/resume');
  expect(op.idempotencyKey).toBeTruthy();
  const retry=state.approvalRetry(op,'approve');
  expect(retry).toBe(op);
  expect(()=>state.approvalRetry(op,'reject')).toThrow();
  evidence[0].conflict.conflict_token='token-new';
  expect(()=>state.approvalOperation(approval,'run-1','approve',evidence,{'draft-1':'token-current'})).toThrow();
  const reject=state.approvalOperation({...approval,data:{...approval.data,expires_at:'2000-01-01T00:00:00Z'}},'run-1','reject',[],{});
  expect(reject.body.decision).toBe('reject');
});

it('shows a scheduling constraint and requires its actual fourteen-day preview without a conflict token',async()=>{
  const state=await import('./AgentApproval');
  const draft:Resource={...calendar,data:{draft_kind:'scheduling_constraint',status:'pending',payload:{constraint_id:null,constraint_revision:null,constraint:{title:'不可安排',timezone:'Asia/Shanghai',starts_at:'2026-11-04T14:00:00+08:00',ends_at:'2026-11-04T17:00:00+08:00',strength:'hard',recurrence:'weekly',weekdays:[3],valid_until:null}}}};
  expect(state.constraintApprovalRange(draft)).toEqual({start:'2026-11-04',end:'2026-11-17'});
  const evidence={action:approval.data.actions[0],resource:draft};
  expect(()=>state.approvalOperation(approval,'run-1','approve',[evidence],{})).toThrow();
  const preview={windows:[{id:'window',kind:'scheduling_constraint',revision:1,data:{starts_at:'2026-11-04T14:00:00+08:00',ends_at:'2026-11-04T17:00:00+08:00'}}],affected_plans:[],active_after_save:true};
  const op=state.approvalOperation(approval,'run-1','approve',[{...evidence,constraint:preview}],{});
  expect(op.body.conflict_tokens).toEqual({});
  expect(op.body.conflict_acknowledged).toEqual([]);
  const q=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}});
  q.setQueryData(['approval','approval-1'],approval);
  q.setQueryData(['approval-draft','draft-1'],draft);
  q.setQueryData(['approval-constraint','approval-1','draft-1',3,'2026-11-04','2026-11-17'],preview);
  const html=renderToStaticMarkup(createElement(QueryClientProvider,{client:q},createElement(state.AgentApproval,{id:'approval-1',runId:'run-1',onResume:()=>{}})));
  expect(html).toContain('不可安排');
  expect(html).toContain('14:00');
  expect(html).toContain('17:00');
  expect(html).toContain('2026-11-17');
  expect(html).toContain('禁排发生预览');
  expect(approveTag(html)).not.toContain(' disabled=');
  q.clear();
});

it('allows complete assignments and program plans without conflict tokens but rejects missing or stale content',async()=>{
  const state=await import('./AgentApproval');
  const assignment:Resource={...calendar,data:{draft_kind:'assignment',status:'pending',payload:{items:[{title:'阅读',requirements:['第一章'],due_at:null}]}}};
  const action=approval.data.actions[0];
  const op=state.approvalOperation(approval,'run-1','approve',[{action,resource:assignment}],{});
  expect(op.body.conflict_tokens).toEqual({});
  expect(()=>state.approvalOperation(approval,'run-1','approve',[{action,resource:{...assignment,revision:4}}],{})).toThrow();
  expect(()=>state.approvalOperation(approval,'run-1','approve',[{action,resource:{...assignment,data:{...assignment.data,payload:{items:[]}}}}],{})).toThrow();
  const plan:Resource={...calendar,data:{draft_kind:'plan',status:'pending',payload:{blocks:[{id:'b',title:'阅读',starts_at:'2026-11-04T14:00:00+08:00',ends_at:'2026-11-04T15:00:00+08:00'}],unscheduled:[]}}};
  const planApproval={...approval,data:{...approval.data,actions:[{name:'commit_plan',args:{draft_id:'draft-1',revision:3}}]}};
  expect(state.approvalOperation(planApproval,'run-1','approve',[{action:planApproval.data.actions[0],resource:plan}],{}).body.conflict_tokens).toEqual({});
  expect(()=>state.approvalOperation(approval,'run-1','approve',[{action,resource:calendar,conflict:report,conflictFetching:true}],{})).toThrow();
});

it('requires current conflict tokens for timetable and course-change facts too',async()=>{
  const state=await import('./AgentApproval');
  const action=approval.data.actions[0];
  for(const draft of [
    {...calendar,data:{draft_kind:'timetable',status:'pending',payload:{courses:[{name:'数学',weekday:3,weeks:[1],periods:[1,2]}]}}},
    {...calendar,data:{draft_kind:'course_change',status:'pending',payload:{course_id:'math',original_date:'2026-11-04',action:'cancel',reason:'教师通知'}}}
  ]) {
    expect(()=>state.approvalOperation(approval,'run-1','approve',[{action,resource:draft}],{})).toThrow();
    expect(state.approvalOperation(approval,'run-1','approve',[{action,resource:draft,conflict:report}],{}).body.conflict_tokens).toEqual({'draft-1':'token-current'});
  }
});

it('preserves task deadline review and guards the current task revision',async()=>{
  const state=await import('./AgentApproval');
  const task:Resource={id:'task-1',kind:'task',revision:5,data:{title:'数学报告',due_at:'2026-11-04T10:00:00+08:00',remedy_due_at:'2026-11-05T10:00:00+08:00',status:'open'}};
  const action={name:'set_task_deadline',args:{task_id:'task-1',revision:5,deadline_type:'due_at',due_at:'2026-11-06T12:00:00+08:00'}};
  const taskApproval={...approval,data:{...approval.data,actions:[action]}};
  expect(state.approvalOperation(taskApproval,'run-1','approve',[{action,resource:task}],{}).body.conflict_tokens).toEqual({});
  expect(()=>state.approvalOperation(taskApproval,'run-1','approve',[{action,resource:{...task,revision:6}}],{})).toThrow();
  const q=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}});
  q.setQueryData(['approval','approval-1'],taskApproval);
  q.setQueryData(['approval-task','task-1'],task);
  q.setQueryData(['settings'],{id:'settings',kind:'settings',revision:1,data:{timezone:'Asia/Shanghai'}});
  const html=renderToStaticMarkup(createElement(QueryClientProvider,{client:q},createElement(state.AgentApproval,{id:'approval-1',runId:'run-1',onResume:()=>{}})));
  expect(html).toContain('数学报告');
  expect(html).toContain('原截止时间');
  expect(html).toContain('新截止时间');
  expect(html).toContain('确认后清除原补救截止时间');
  expect(approveTag(html)).not.toContain(' disabled=');
  q.clear();
});

it('keeps rejection reachable when a preview response is incomplete',async()=>{
  const html=await render(calendar,{conflict_token:'incomplete'});
  expect(approveTag(html)).toContain(' disabled=');
  expect(html.match(/<button[^>]*>拒绝<\/button>/)?.[0]).not.toContain(' disabled=');
});
