import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './api';
import { Button } from './components/ui/button';
import { navigate } from './drafts';
import { PlanReview } from './Today';
import type { Resource } from './types';
import { proactiveCategories, proactivePreferencePayload, proactiveOperation, proactiveActionOperation, visibleProactive, type ProactivePreferences, type ProactivePreferenceView, type ProactiveOperation, type ProactiveSuggestion, type ProactiveList, type ProactiveActionResult, type ProactiveAction } from './proactive-state';

function useProactiveCommand(onResult?:(result:unknown)=>void) {
  const q=useQueryClient();
  const [pending,setPending]=useState<ProactiveOperation|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const pendingRef=useRef<ProactiveOperation|null>(null),busyRef=useRef(false),resultRef=useRef(onResult);
  resultRef.current=onResult;
  const run=useCallback(async(operation?:ProactiveOperation,retry=false)=>{
    if(busyRef.current||(pendingRef.current&&!retry))return;
    const request=pendingRef.current??operation;
    if(!request)return;
    pendingRef.current=request;setPending(request);busyRef.current=true;setBusy(true);setError('');setMessage('');
    try {
      const result=await api<unknown>(request.path,{method:request.method,headers:{'Idempotency-Key':request.idempotencyKey},body:JSON.stringify(request.body)});
      pendingRef.current=null;setPending(null);
      if(request.path==='/proactive/refresh') q.setQueryData(['proactive','suggestions'],result);
      else await q.invalidateQueries({queryKey:['proactive']});
      resultRef.current?.(result);
    }catch(e){
      if(e instanceof ApiError&&e.status>=400&&e.status<500){
        pendingRef.current=null;setPending(null);
        if(e.status===409)await q.invalidateQueries({queryKey:['proactive']});
      }
      setError(String(e));
    }finally{busyRef.current=false;setBusy(false);}
  },[q]);
  return {pending,busy,error,message,setError,setMessage,run};
}
function CommandStatus({command}:{command:ReturnType<typeof useProactiveCommand>}) {
  return <>{command.pending&&<p role="status">{command.busy?'正在处理…':'结果尚未确认；重试保留原版本、参数和请求标识。'}</p>}{command.pending&&!command.busy&&<Button type="button" variant="outline" onClick={()=>void command.run(undefined,true)}>重试同一次请求</Button>}{command.error&&<p role="alert">{command.error}</p>}{command.message&&<p role="status">{command.message}</p>}</>;
}
export function ProactiveSettings() {
  const preferences=useQuery({queryKey:['proactive','preferences'],queryFn:()=>api<ProactivePreferenceView>('/proactive/preferences')});
  const [editor,setEditor]=useState<{revision:number;data:ProactivePreferences}|null>(null);
  const command=useProactiveCommand(()=>{setEditor(null);command.setMessage('主动建议设置已保存。');});
  const locked=command.busy||!!command.pending;
  function change(patch:Partial<ProactivePreferences>){if(editor)setEditor({...editor,data:{...editor.data,...patch}});}
  function quiet(index:number,patch:Partial<NonNullable<ProactivePreferences['quiet_hours']>[number]>){if(editor)change({quiet_hours:editor.data.quiet_hours?.map((w,i)=>i===index?{...w,...patch}:w)??null});}
  async function save(){
    if(!editor)return;
    try {await command.run(proactiveOperation('PUT','/proactive/preferences',proactivePreferencePayload(editor.revision,editor.data)));}
    catch(e){command.setError(String(e));}
  }
  return <section aria-label="主动建议设置"><h3>主动建议设置</h3>
    <p>应用内无声建议。开启后，仅在应用可见且活跃时核对任务风险和真实空档。</p>
    {preferences.isPending&&<p role="status">正在读取主动建议设置…</p>}
    {preferences.error&&<><p role="alert">读取设置失败：{String(preferences.error)}</p><Button type="button" variant="outline" onClick={()=>void preferences.refetch()}>重试读取设置</Button></>}
    {preferences.data&&<><p>{preferences.data.data.enabled?'已开启':'已关闭'} · {preferences.data.data.quiet_hours===null?'安静时段未知（未设置）':preferences.data.data.quiet_hours.length?'已设置明确安静时段':'已明确不设安静时段'}</p>
      {!editor&&<Button type="button" variant="outline" disabled={locked} onClick={()=>setEditor({revision:preferences.data.revision,data:structuredClone(preferences.data.data)})}>编辑主动建议设置</Button>}</>}
    {editor&&<form onSubmit={event=>{event.preventDefault();void save();}}><fieldset disabled={locked}><legend>频率与安静时段</legend>
      <label><input type="checkbox" checked={editor.data.enabled} onChange={event=>change({enabled:event.target.checked})}/>开启主动建议</label>
      <fieldset><legend>建议类别</legend>{Object.entries(proactiveCategories).map(([category,label])=><label key={category}><input type="checkbox" checked={editor.data.categories[category as keyof typeof proactiveCategories]} onChange={event=>change({categories:{...editor.data.categories,[category]:event.target.checked}})}/>{label}</label>)}</fieldset>
      <label>安静时段时区（未知可留空）<input placeholder="Asia/Shanghai" value={editor.data.timezone??''} onChange={event=>change({timezone:event.target.value||null})}/></label>
      <label>安静时段设置<select aria-label="安静时段设置" value={editor.data.quiet_hours===null?'unknown':editor.data.quiet_hours.length?'specified':'none'} onChange={event=>change({quiet_hours:event.target.value==='unknown'?null:event.target.value==='none'?[]:[{weekdays:[],start:'',end:''}]})}><option value="unknown">未知（未设置）</option><option value="none">明确不设安静时段</option><option value="specified">设置明确时段</option></select></label>
      <p>星期表示开始日；例如星期日22:00至02:00包含星期一凌晨。区间含开始、不含结束；不会推断睡眠时间。</p>
      {editor.data.quiet_hours?.map((window,index)=><fieldset key={index}><legend>安静时段 {index+1}</legend><div>{['一','二','三','四','五','六','日'].map((label,i)=><label key={i}><input type="checkbox" checked={window.weekdays.includes(i+1)} onChange={event=>quiet(index,{weekdays:event.target.checked?[...window.weekdays,i+1].sort():window.weekdays.filter(day=>day!==i+1)})}/>星期{label}</label>)}</div>
        <label>安静开始<input type="time" required value={window.start} onChange={event=>quiet(index,{start:event.target.value})}/></label><label>安静结束<input type="time" required value={window.end} onChange={event=>quiet(index,{end:event.target.value})}/></label>
        <Button type="button" variant="outline" onClick={()=>change({quiet_hours:editor.data.quiet_hours!.filter((_,i)=>i!==index)})}>移除此时段</Button></fieldset>)}
      {editor.data.quiet_hours!==null&&<Button type="button" variant="outline" onClick={()=>change({quiet_hours:[...editor.data.quiet_hours!,{weekdays:[],start:'',end:''}]})}>添加安静时段</Button>}
      <Button type="submit" variant="outline">确认保存主动建议设置</Button><Button type="button" variant="outline" onClick={()=>setEditor(null)}>取消编辑</Button>
    </fieldset></form>}
    <CommandStatus command={command}/>
  </section>;
}
function useAppActive() {
  const [active,setActive]=useState(()=>typeof document==='undefined'||(document.visibilityState==='visible'&&document.hasFocus()));
  useEffect(()=>{
    const update=()=>setActive(document.visibilityState==='visible'&&document.hasFocus());
    window.addEventListener('focus',update);window.addEventListener('blur',update);document.addEventListener('visibilitychange',update);update();
    return ()=>{window.removeEventListener('focus',update);window.removeEventListener('blur',update);document.removeEventListener('visibilitychange',update);};
  },[]);
  return active;
}
export type ProactiveSuggestionsProps={onOpenTask?:(taskId:string)=>void;onOpenDraft?:(draft:Resource)=>void};
export function ProactiveSuggestions({onOpenTask,onOpenDraft}:ProactiveSuggestionsProps={}) {
  const q=useQueryClient();
  const list=useQuery({queryKey:['proactive','suggestions'],queryFn:()=>api<ProactiveList>('/proactive/suggestions')});
  const active=useAppActive(),[showHistory,setShowHistory]=useState(false),[draftId,setDraftId]=useState<string|null>(null),[openedTask,setOpenedTask]=useState<string|null>(null);
  const command=useProactiveCommand(result=>{
    const response=result as Partial<ProactiveActionResult>;
    if(response.draft){setDraftId(response.draft.id);void q.invalidateQueries({queryKey:['drafts']});command.setMessage('已生成待确认计划草稿；请核对后使用原确认入口。');}
    if(response.open_task_id){setOpenedTask(response.open_task_id);command.setMessage(`已打开关联任务：${response.open_task_id}。打开详情不代表完成。`);if(onOpenTask)onOpenTask(response.open_task_id);else navigate('作业');}
  });
  const draft=useQuery({queryKey:['proactive','draft',draftId],queryFn:()=>api<Resource>(`/drafts/${draftId}`),enabled:!!draftId});
  useEffect(()=>{if(draft.data?.data.status==='pending'&&onOpenDraft)onOpenDraft(draft.data);},[draft.data,onOpenDraft]);
  const enabled=list.data?.preferences.data.enabled??false;
  const run=command.run;
  useEffect(()=>{
    if(!enabled||!active)return;
    void run(proactiveOperation('POST','/proactive/refresh',{app_active:true}));
    const interval=window.setInterval(()=>void run(proactiveOperation('POST','/proactive/refresh',{app_active:true})),60000);
    return ()=>window.clearInterval(interval);
  },[enabled,active,run]);
  const locked=command.busy||!!command.pending;
  const visible=visibleProactive(list.data?.suggestions??[],active);
  const history=(list.data?.suggestions??[]).filter(item=>item.data.state!=='pending');
  function act(item:ProactiveSuggestion,action:ProactiveAction,options:{snooze_minutes?:number;accept_mode?:'details'|'replan'}={}){void command.run(proactiveActionOperation(item,action,options));}
  return <section aria-label="主动建议"><h3>主动建议</h3><p>应用内无声 · 风险和空档由已确认资料计算。缺少执行记录时，实际投入保持未知。</p>
    {list.isPending&&<p role="status">正在读取主动建议…</p>}
    {list.error&&<><p role="alert">读取建议失败：{String(list.error)}</p><Button type="button" variant="outline" onClick={()=>void list.refetch()}>重试读取建议</Button></>}
    <Button type="button" variant="outline" disabled={locked||!enabled||!active} onClick={()=>void command.run(proactiveOperation('POST','/proactive/refresh',{app_active:true}))}>刷新建议</Button>
    {list.data&&!enabled&&<p>主动建议已关闭；可在设置中明确开启。</p>}{enabled&&!active&&<p>应用当前未活跃，暂停自动刷新与展示。</p>}{list.data?.suppression==='quiet_hours'&&enabled&&<p>当前处于已设置的安静时段，建议暂不展示。</p>}
    {list.data?.capacity&&enabled&&active&&list.data.suppression!=='quiet_hours'&&<p>甲核对共享容量上限 {list.data.capacity.capacity_upper_bound_minutes} 分钟 · 预计所需 {list.data.capacity.required_minutes} 分钟 · 未排入 {list.data.capacity.unallocated_minutes} 分钟 · 耗时未知 {list.data.capacity.unknown_estimate_count} 项。容量上限不等于实际投入。</p>}
    {enabled&&active&&!visible.length&&list.data?.suppression!=='quiet_hours'&&<p>暂无需要展示的新建议。已处理的同一原因会保持状态。</p>}
    {visible.map(item=><article className="card" key={item.id} aria-label={`建议：${item.data.title}`}><h4>{item.data.title}</h4><p>{proactiveCategories[item.data.category]}</p><ul>{item.data.reasons.map((reason,index)=><li key={index}>{reason}</li>)}</ul>
      <details><summary>核对建议依据与缺口</summary><ul>{item.data.gaps.map((gap,index)=><li key={index}>{gap}</li>)}</ul>{item.data.sources.map(source=><p key={source.id}>来源 {source.kind} · {source.id} · 版本 {source.revision}</p>)}<p>资料版本 {item.data.source_revision} · 仅用于当前校对</p></details>
      {item.data.task_id&&<Button type="button" variant="outline" disabled={locked} onClick={()=>act(item,'accept',{accept_mode:'details'})}>打开关联任务详情</Button>}
      <Button type="button" variant="outline" disabled={locked} onClick={()=>act(item,'accept',{accept_mode:'replan'})}>生成待确认计划草稿</Button>
      <Button type="button" variant="outline" disabled={locked} onClick={()=>act(item,'snooze',{snooze_minutes:30})}>稍后30分钟</Button><Button type="button" variant="outline" disabled={locked} onClick={()=>act(item,'dismiss')}>关闭本条</Button><Button type="button" variant="outline" disabled={locked} onClick={()=>act(item,'disable_category')}>关闭此类建议</Button>
    </article>)}
    {history.length>0&&<><Button type="button" variant="outline" onClick={()=>setShowHistory(!showHistory)}>{showHistory?'收起':'查看'}已处理建议（{history.length}）</Button>{showHistory&&<ul>{history.map(item=><li key={item.id}>{item.data.title} · {{snoozed:'稍后处理',dismissed:'已关闭',accepted:'已采纳',resolved:'问题已消失',superseded:'依据已变化',pending:'待处理'}[item.data.state]}{item.data.state==='snoozed'&&item.data.snoozed_until?` · 至 ${new Date(item.data.snoozed_until).toLocaleString()}`:''}</li>)}</ul>}</>}
    {openedTask&&<p>关联任务：{openedTask}。任务状态与实际完成请在详情中确认。</p>}
    {draftId&&<section aria-label="主动建议关联计划"><h4>建议关联的计划草稿</h4>{draft.isPending&&<p role="status">正在核对最新草稿…</p>}{draft.error&&<><p role="alert">读取草稿失败：{String(draft.error)}</p><Button type="button" variant="outline" onClick={()=>void draft.refetch()}>重试读取草稿</Button></>}{draft.data&&draft.data.data.status!=='pending'&&<p>此草稿已{draft.data.data.status==='confirmed'?'确认':'失效或被替代'}，请刷新建议核对当前状态。</p>}{draft.data?.data.status==='pending'&&!onOpenDraft&&<PlanReview draft={draft.data}/>}</section>}
    <CommandStatus command={command}/>
  </section>;
}
export default ProactiveSuggestions;
