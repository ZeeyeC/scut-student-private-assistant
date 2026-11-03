import {useRef, useState} from 'react';
import {useQueries, useQuery, useQueryClient} from '@tanstack/react-query';
import {api, ApiError} from './api';
import type {Resource} from './types';
import {Button} from './components/ui/button';
import {ConflictReview, type ConflictReport} from './ConflictReview';
import {constraintInput} from './constraint-time';

const labels:Record<string,string>={commit_import:'确认保存',commit_plan:'确认保存计划',set_task_status:'更新作业状态',set_task_deadline:'更新截止时间',delete_fixed_event:'删除固定事项'};
const conflictKinds=new Set(['calendar_event','timetable','timetable_recognition','timetable_text','course_change']);
type ApprovalAction={name:string;args:Record<string,any>};
type ConstraintPreview={windows:Resource[];affected_plans:Resource[];active_after_save:boolean};
export type ApprovalEvidence={action:ApprovalAction;resource?:Resource;fetching?:boolean;error?:unknown;conflict?:ConflictReport;conflictFetching?:boolean;conflictError?:unknown;constraint?:ConstraintPreview;constraintFetching?:boolean;constraintError?:unknown};
type Decision='approve'|'reject';
export type ApprovalOperation={path:string;idempotencyKey:string;body:{approval_id:string;revision:number;decision:Decision;conflict_tokens:Record<string,string>;conflict_acknowledged:string[]}};

export function constraintApprovalRange(draft:Resource) {
  const c=draft.data.payload?.constraint;
  if(!c?.starts_at || !c.timezone) throw new Error('禁排内容缺少日期或时区');
  const start=constraintInput(c.starts_at,c.timezone).slice(0,10);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(start)) throw new Error('禁排日期无效');
  const end=new Date(start+'T12:00:00Z');
  end.setUTCDate(end.getUTCDate()+13);
  return {start,end:end.toISOString().slice(0,10)};
}
function constraintRange(draft?:Resource) {try{return draft?constraintApprovalRange(draft):null;}catch{return null;}}
function interval(p:Record<string,any>) {return !!p.starts_at && !!p.ends_at && Number.isFinite(Date.parse(p.starts_at)) && Date.parse(p.ends_at)>Date.parse(p.starts_at);}
function hasContent(draft:Resource) {
  const p=draft.data.payload;
  if(!p || typeof p!=='object')return false;
  switch(draft.data.draft_kind) {
    case 'calendar_event':return !!p.title?.trim() && interval(p);
    case 'timetable':return Array.isArray(p.courses) && p.courses.length>0 && p.courses.every((c:Record<string,any>)=>!!c.name?.trim());
    case 'timetable_text':case 'timetable_recognition':return Array.isArray(p.candidates) && p.candidates.length>0;
    case 'course_change':return !!p.course_id && !!p.original_date && ['move','cancel','restore'].includes(p.action) && (p.action!=='move' || interval(p));
    case 'scheduling_constraint':return !!p.constraint?.title?.trim() && interval(p.constraint) && !!constraintRange(draft);
    case 'assignment':return Array.isArray(p.items) && p.items.length>0 && p.items.every((i:Record<string,any>)=>!!i.title?.trim());
    case 'decomposition':return Array.isArray(p.steps) && p.steps.length>0 && p.steps.every((s:Record<string,any>)=>!!s.title?.trim());
    case 'plan':return Array.isArray(p.blocks) && Array.isArray(p.unscheduled) && (p.blocks.length>0 || p.removed_blocks?.length>0);
    default:return false;
  }
}
function needsAcknowledgement(report:ConflictReport) {return report.conflict_count>0 || report.pending_count>0 || report.complete!==true;}
function validConflict(report?:ConflictReport) {return !!report && typeof report.conflict_token==='string' && !!report.conflict_token && Array.isArray(report.issues) && Number.isInteger(report.conflict_count) && report.conflict_count>=0 && Number.isInteger(report.pending_count) && report.pending_count>=0;}

export function approvalOperation(approval:Resource,runId:string,decision:Decision,evidence:ApprovalEvidence[],acknowledged:Record<string,string>):ApprovalOperation {
  if(approval.data.run_id && approval.data.run_id!==runId)throw new Error('确认与当前运行不符，请刷新后重试');
  const tokens:Record<string,string>={};
  const acknowledgements=new Set<string>();
  if(decision==='approve') {
    if(!Number.isFinite(Date.parse(approval.data.expires_at)) || Date.parse(approval.data.expires_at)<=Date.now())throw new Error('此确认已过期，请拒绝后重新提出请求');
    if(approval.data.decision)throw new Error('此确认已作出决定，请刷新核对');
    const actions=approval.data.actions;
    if(!Array.isArray(actions) || !actions.length || evidence.length!==actions.length)throw new Error('待确认内容尚未完整读取');
    if(actions.length>1 && evidence.some(entry=>entry.action.name==='commit_import' && conflictKinds.has(entry.resource?.data.draft_kind)))throw new Error('时间事实修改需要逐项确认。请拒绝本轮后逐项提出；当前尚未执行本轮操作。');
    for(let i=0;i<evidence.length;i++) {
      const entry=evidence[i], action=actions[i] as ApprovalAction, resource=entry.resource;
      if(JSON.stringify(entry.action)!==JSON.stringify(action))throw new Error('待确认参数已变化，请刷新核对');
      if(entry.fetching || entry.error || !resource)throw new Error('准确内容尚未读取，无法批准');
      if(resource.revision!==action.args.revision)throw new Error('内容版本已变化，请拒绝后重新提出请求');
      if(action.name==='delete_fixed_event') {
        if(actions.length!==1 || resource.kind!=='fixed_event' || resource.id!==action.args.event_id || !resource.data.title)throw new Error('请逐项核对要删除的固定事项');
      } else if(action.args.draft_id) {
        if(!['commit_import','commit_plan'].includes(action.name))throw new Error('尚不支持批准这项操作');
        if(resource.kind!=='draft' || resource.id!==action.args.draft_id || resource.data.status!=='pending' || !hasContent(resource))throw new Error('草稿内容缺失或已失效，无法批准');
        const kind=resource.data.draft_kind;
        if(conflictKinds.has(kind)) {
          if(entry.conflictFetching || entry.conflictError || !validConflict(entry.conflict))throw new Error('请先完成当前冲突检查');
          const report=entry.conflict!;
          tokens[resource.id]=report.conflict_token!;
          if(needsAcknowledgement(report)) {
            if(acknowledged[resource.id]!==report.conflict_token)throw new Error('请勾选已核对当前冲突或未知信息');
            acknowledgements.add(resource.id);
          }
        }
        if(kind==='scheduling_constraint' && (entry.constraintFetching || entry.constraintError || !entry.constraint || !Array.isArray(entry.constraint.windows) || !Array.isArray(entry.constraint.affected_plans) || typeof entry.constraint.active_after_save!=='boolean'))throw new Error('请先读取完整的14天禁排预览');
      } else {
        if(resource.kind!=='task' || resource.id!==action.args.task_id || !resource.data.title)throw new Error('待办内容缺失，无法批准');
        if(action.name==='set_task_deadline') {
          if(!['due_at','remedy_due_at'].includes(action.args.deadline_type) || (action.args.due_at!==null && !Number.isFinite(Date.parse(action.args.due_at))))throw new Error('新截止时间无效，请拒绝后重新设置');
        } else if(action.name!=='set_task_status' || !['open','completed','archived'].includes(action.args.status))throw new Error('尚不支持批准这项操作');
      }
    }
  }
  return {path:`/agent/runs/${runId}/resume`,idempotencyKey:crypto.randomUUID(),body:{approval_id:approval.id,revision:approval.revision,decision,conflict_tokens:tokens,conflict_acknowledged:[...acknowledgements]}};
}
export function approvalRetry(operation:ApprovalOperation,decision:Decision) {
  if(operation.body.decision!==decision)throw new Error('上次决定的结果尚未确认，请先重试同一次操作');
  return operation;
}

type ApprovalProps={id:string;runId:string;onResume:()=>void};
export function AgentApproval(props:ApprovalProps) {
  return <ApprovalContent key={`${props.id}:${props.runId}`} {...props}/>;
}
function ApprovalContent({id,runId,onResume}:ApprovalProps) {
  const q=useQueryClient();
  const [error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [pending,setPending]=useState<ApprovalOperation|null>(null);
  const [acknowledged,setAcknowledged]=useState<Record<string,string>>({});
  const busyRef=useRef(false);
  const approval=useQuery({queryKey:['approval',id],queryFn:()=>api<Resource>('/agent/approvals/'+id),refetchInterval:15000});
  const actions:ApprovalAction[]=Array.isArray(approval.data?.data.actions)?approval.data.data.actions:[];
  const sources=useQueries({queries:actions.map(action=>{
    const [kind, target]=action.name==='delete_fixed_event'
      ? ['fixed-events',action.args.event_id]
      : action.args.draft_id ? ['drafts',action.args.draft_id] : ['tasks',action.args.task_id];
    return {queryKey:[kind==='fixed-events'?'approval-fixed-event':kind==='drafts'?'approval-draft':'approval-task',target],queryFn:()=>api<Resource>(`/${kind}/${target}`),enabled:!!target,refetchInterval:15000};
  })});
  const conflicts=useQueries({queries:actions.map((action,i)=>{
    const draft=sources[i].data;
    return {queryKey:['approval-conflict',id,action.args.draft_id,draft?.revision],queryFn:()=>api<ConflictReport>(`/drafts/${draft!.id}/conflict-preview`,{method:'POST',body:JSON.stringify({revision:draft!.revision,payload:draft!.data.payload})}),enabled:!!draft && !sources[i].error && draft.revision===action.args.revision && conflictKinds.has(draft.data.draft_kind),refetchInterval:15000};
  })});
  const constraints=useQueries({queries:actions.map((action,i)=>{
    const draft=sources[i].data, range=constraintRange(draft?.data.draft_kind==='scheduling_constraint'?draft:undefined);
    return {queryKey:['approval-constraint',id,action.args.draft_id,draft?.revision,range?.start,range?.end],queryFn:()=>api<ConstraintPreview>(`/drafts/${draft!.id}/constraint-preview?start=${range!.start}&end=${range!.end}`,{method:'POST',body:JSON.stringify({revision:draft!.revision,payload:draft!.data.payload})}),enabled:!!range && !!draft && !sources[i].error && draft.revision===action.args.revision,refetchInterval:15000};
  })});
  const settings=useQuery({queryKey:['settings'],queryFn:()=>api<Resource>('/settings')});
  const evidence:ApprovalEvidence[]=actions.map((action,i)=>({action,resource:sources[i].data,fetching:sources[i].isFetching,error:sources[i].error,conflict:conflicts[i].data,conflictFetching:conflicts[i].isFetching,conflictError:conflicts[i].error,constraint:constraints[i].data,constraintFetching:constraints[i].isFetching,constraintError:constraints[i].error}));
  let blocked='正在读取确认内容';
  if(approval.data) {
    try {if(approval.isFetching || approval.error)throw new Error('正在核对确认请求');approvalOperation(approval.data,runId,'approve',evidence,acknowledged);blocked='';}
    catch(e) {blocked=e instanceof Error?e.message:String(e);}
  }
  async function decide(decision:Decision) {
    if(busyRef.current)return;
    setError('');busyRef.current=true;setBusy(true);
    try {
      const operation=pending?approvalRetry(pending,decision):approvalOperation(approval.data || await api<Resource>('/agent/approvals/'+id),runId,decision,evidence,acknowledged);
      setPending(operation);
      try {
        await api(operation.path,{method:'POST',headers:{'Idempotency-Key':operation.idempotencyKey},body:JSON.stringify(operation.body)});
        setPending(null);void q.invalidateQueries();onResume();
      } catch(e) {
        if(e instanceof ApiError && e.status>=400 && e.status<500){setPending(null);setAcknowledged({});void q.invalidateQueries();}
        throw e;
      }
    } catch(e) {setError(String(e));}
    finally {busyRef.current=false;setBusy(false);}
  }
  return <section className="card confirm" aria-label="助手操作确认">
    <h2>这一步需要你确认</h2>
    <p>批准后才会执行所列操作。</p>
    {approval.error && <p role="alert">确认请求读取失败：{String(approval.error)}</p>}
    {evidence.map((entry,i)=><div key={`${entry.action.name}:${entry.action.args.draft_id || entry.action.args.task_id || entry.action.args.event_id}:${i}`}>
      <h3>{labels[entry.action.name] || entry.action.name}</h3>
      {!!entry.error && <p role="alert">准确内容读取失败：{String(entry.error)}</p>}
      {!entry.resource?<p role="status">正在读取准确内容…</p>:<>
        <p>当前内容版本 {entry.resource.revision} · 请求版本 {entry.action.args.revision}</p>
        {entry.resource.revision!==entry.action.args.revision && <p role="alert">内容版本已变化，请拒绝后重新提出请求。</p>}
        {entry.action.args.draft_id?<ApprovalDraft draft={entry.resource}/>:<ApprovalTask resource={entry.resource} args={entry.action.args} name={entry.action.name} timezone={settings.data?.data.timezone || 'Asia/Shanghai'}/>}
        {entry.conflictFetching && <p role="status">正在读取当前冲突检查…</p>}
        {!!entry.conflictError && <p role="alert">冲突预览失败：{String(entry.conflictError)}</p>}
        {validConflict(entry.conflict) && <ConflictReview report={entry.conflict!}/>}
        {validConflict(entry.conflict) && needsAcknowledgement(entry.conflict!) && <label className="check"><input type="checkbox" disabled={busy || !!pending || entry.conflictFetching} checked={acknowledged[entry.resource.id]===entry.conflict!.conflict_token} onChange={event=>setAcknowledged({...acknowledged,[entry.resource!.id]:event.target.checked?entry.conflict!.conflict_token!:''})}/>我已核对当前冲突和未知信息，仍按这些事实保存</label>}
        {entry.resource.data.draft_kind==='scheduling_constraint' && <>
          <p>预览14天：{constraintRange(entry.resource)?.start || '日期无效'} 至 {constraintRange(entry.resource)?.end || '日期无效'}</p>
          {entry.constraintFetching && <p role="status">正在读取禁排发生预览…</p>}
          {!!entry.constraintError && <p role="alert">禁排预览失败：{String(entry.constraintError)}</p>}
          {entry.constraint && Array.isArray(entry.constraint.windows) && Array.isArray(entry.constraint.affected_plans) && <div aria-label="禁排发生预览">
            {!entry.constraint.windows.length && <p>这14天内没有该规则的发生时间。</p>}
            {entry.constraint.windows.map(window=><p key={window.id}>{when(window.data.starts_at,entry.resource!.data.payload.constraint.timezone)} 至 {when(window.data.ends_at,entry.resource!.data.payload.constraint.timezone)}</p>)}
            {entry.constraint.affected_plans.map(plan=><p key={plan.id}>与已有安排重叠：{plan.data.title || '学习安排'}{plan.data.locked?'（已锁定）':''}；确认新计划前保留原样。</p>)}
            {!entry.constraint.active_after_save && <p>该规则保存后仍保持停用。</p>}
          </div>}
        </>}
      </>}
    </div>)}
    {blocked && <p role="status">{blocked}</p>}
    <Button type="button" disabled={busy || !!pending || !!blocked} onClick={()=>void decide('approve')}>批准并执行</Button>
    <Button type="button" variant="outline" disabled={busy} onClick={()=>void decide('reject')}>拒绝</Button>
    <Button type="button" variant="outline" disabled={busy || !!pending} onClick={()=>void q.invalidateQueries()}>重新读取内容与预览</Button>
    {pending && !busy && <><p role="status">决定结果尚未确认；重试会使用同一请求核对，避免重复执行。</p><Button type="button" variant="outline" onClick={()=>void decide(pending.body.decision)}>重试同一次决定</Button></>}
    {error && <p role="alert">{error}</p>}
  </section>;
}

function when(value:string,zone='Asia/Shanghai') {
  if(!value || !Number.isFinite(Date.parse(value)))return '时间待核对';
  try{return new Date(value).toLocaleString('zh-CN',{timeZone:zone,hour12:false});}catch{return '时区待核对';}
}
function ApprovalDraft({draft}:{draft:Resource}) {
  const p=draft.data.payload || {},zone=p.timezone || p.constraint?.timezone || 'Asia/Shanghai';
  return <div aria-label="待批准的准确草稿">
    {p.starts_at && <p>{p.title} · {when(p.starts_at,zone)} 至 {when(p.ends_at,zone)}</p>}
    {p.course_id && <p>课程 {p.course_id} · 原日期 {p.original_date} · {{move:'调课',cancel:'停课',restore:'恢复原课'}[p.action as 'move'|'cancel'|'restore']} · {p.location || '地点未调整'} · {p.reason}</p>}
    {p.items?.map((item:Record<string,any>,i:number)=><p key={i}>{item.title} · {item.due_at?when(item.due_at,zone):'截止时间待确认'}<br/>{item.requirements?.join('；')}</p>)}
    {p.courses?.map((course:Record<string,any>,i:number)=><p key={i}>{course.name} · 星期{course.weekday} · 第 {course.weeks?.join(',')} 周 · 第 {course.periods?.join(',')} 节 · {course.location}</p>)}
    {p.candidates?.map((course:Record<string,any>,i:number)=><p key={course.candidate_id || i}>{course.name || '课程名待确认'} · 星期{course.weekday || '待确认'} · {course.weeks_text || '周次待确认'} · 第 {course.periods?.join(',')} 节 · {course.location || '地点待确认'}{course.excluded?'（已排除）':''}{!course.reviewed?'（尚未校对）':''}</p>)}
    {p.constraint && <section aria-label="待批准禁排规则"><h4>{p.constraint.title}</h4><p>{p.constraint.strength==='soft'?'软偏好（可让步）':'硬禁排'} · {p.constraint.recurrence==='weekly'?`每周${p.constraint.weekdays?.map((d:number)=>['一','二','三','四','五','六','日'][d-1]).join('、')}`:'仅这一次'}</p><p>{when(p.constraint.starts_at,zone)} 至 {when(p.constraint.ends_at,zone)}（{zone}）</p><p>有效期：{p.constraint.valid_until || '长期有效'}。确认后影响后续规划，已保存安排需重新规划并确认。</p></section>}
    {p.steps?.map((step:Record<string,any>,i:number)=><p key={i}>{step.title} · 预计 {step.estimated_minutes} 分钟 · {step.acceptance_criteria?.join('；')}</p>)}
    {p.blocks?.map((block:Record<string,any>)=><p key={block.id}><strong>{block.title || '学习安排'}</strong> · {when(block.starts_at,zone)} 至 {when(block.ends_at,zone)}{block.locked?' · 已锁定':''}</p>)}
    {p.warnings?.map((warning:string,i:number)=><p role="alert" key={i}>{warning}</p>)}
    {p.removed_blocks?.map((block:Record<string,any>)=><p key={block.id}>移除旧建议：{block.title} · {block.reason}</p>)}
    {p.unscheduled?.map((work:Record<string,any>,i:number)=><p key={i}>{work.title}：{work.remaining_minutes==null?'':`未安排 ${work.remaining_minutes} 分钟 · `}{work.reason}</p>)}
  </div>;
}
function ApprovalTask({resource:task,args,name,timezone}:{resource:Resource;args:Record<string,any>;name:string;timezone:string}) {
  function deadline(value:string|null|undefined) {return value?when(value,timezone):'待确认';}
  if(name==='delete_fixed_event') return <p>删除「{task.data.title}」 · {when(task.data.starts_at,timezone)} 至 {when(task.data.ends_at,timezone)}</p>;
  if(name==='set_task_deadline') {
    const recovery=args.deadline_type==='remedy_due_at';
    return <div><p>{task.data.title} · 版本 {args.revision}</p><p>原{recovery?'补救':''}截止时间：{deadline(task.data[args.deadline_type])}</p><p>新{recovery?'补救':''}截止时间：{deadline(args.due_at)}</p><p>时区：{timezone}</p>{!recovery && task.data.remedy_due_at && <p>确认后清除原补救截止时间：{deadline(task.data.remedy_due_at)}</p>}<p>已有步骤和学习安排保留；旧计划与拆解草稿会失效，请重新生成。</p></div>;
  }
  return <p>{task.data.title} · 版本 {args.revision} · 将状态改为 {args.status==='completed'?'已完成':args.status==='archived'?'已归档':'进行中'}</p>;
}
