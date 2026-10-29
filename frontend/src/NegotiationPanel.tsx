import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { Button } from "./components/ui/button";
import { PlanReview } from "./Today";
import type { Resource } from "./types";
import { emptyIntentForm, intentConditions, intentForm, negotiationOperation, selectIntentId, type IntentForm, type IntentInterval, type NegotiationOperation } from "./negotiation-state";

function Intervals({ title, rows, timezone, disabled, onChange }: { title: string; rows: IntentInterval[]; timezone: string; disabled: boolean; onChange: (rows:IntentInterval[])=>void }) {
  return <fieldset disabled={disabled}><legend>{title}</legend>
    <p>选择本轮明确的开始与结束时间，按设置时区 {timezone || "正在读取"} 保存。</p>
    {rows.map((row,index)=><div className="grid2" key={index}>
      <label>{title}开始 {index+1}<input type="datetime-local" value={row.starts_at} onChange={e=>onChange(rows.map((r,i)=>i===index?{...r,starts_at:e.target.value}:r))} /></label>
      <label>{title}结束 {index+1}<input type="datetime-local" value={row.ends_at} onChange={e=>onChange(rows.map((r,i)=>i===index?{...r,ends_at:e.target.value}:r))} /></label>
      <Button type="button" variant="outline" onClick={()=>onChange(rows.filter((_,i)=>i!==index))}>移除{title} {index+1}</Button>
    </div>)}
    <Button type="button" variant="outline" onClick={()=>onChange([...rows,{starts_at:"",ends_at:""}])}>添加{title}</Button>
  </fieldset>;
}

export function NegotiationPanel({onDraft}:{onDraft?:(draft:Resource)=>void} = {}) {
  const q=useQueryClient();
  const me=useQuery({queryKey:["me"],queryFn:()=>api<{id:string}>("/me")});
  const settings=useQuery({queryKey:["settings"],queryFn:()=>api<Resource>("/settings")});
  const intents=useQuery({queryKey:["planning-intents"],queryFn:()=>api<Resource[]>("/planning-intents")});
  const blocks=useQuery({queryKey:["plan-blocks"],queryFn:()=>api<Resource[]>("/plan-blocks")});
  const [selected,setSelected]=useState<string|null>(null);
  const [form,setForm]=useState<IntentForm>(emptyIntentForm);
  const [pending,setPending]=useState<NegotiationOperation|null>(null);
  const [busy,setBusy]=useState(false), [error,setError]=useState(""), [message,setMessage]=useState("");
  const busyRef=useRef(false), loadedRef=useRef<string|null>(null);
  const owner=me.data?.id;
  const storageKey=owner?`planning-negotiation:${owner}`:null;
  const selectedId=selectIntentId(intents.data??[],selected);
  const current=intents.data?.find(r=>r.id===selectedId);
  const locked=busy||!!pending;
  const ready=!!(owner&&settings.data&&intents.data&&blocks.data&&!settings.isFetching&&!intents.isFetching&&!blocks.isFetching);
  const preview=current?.data.preview;
  const draftId=current?.data.choice?.draft_id;
  const chosenDraft=useQuery({queryKey:["negotiation-draft",draftId],queryFn:()=>api<Resource>(`/drafts/${draftId}`),enabled:!!draftId});
  const currentDraft=chosenDraft.data;

  useEffect(()=>{
    if (!storageKey || !intents.data || loadedRef.current===storageKey) return;
    loadedRef.current=storageKey;
    let remembered: {selected?:string;pending?:NegotiationOperation}|null=null;
    try {remembered=JSON.parse(sessionStorage.getItem(storageKey)??"null");} catch { /* unreadable cache is disposable */ }
    const id=selectIntentId(intents.data,remembered?.selected??null);
    setSelected(id);
    const item=intents.data.find(i=>i.id===id);
    setForm(item?intentForm(item.data.conditions):emptyIntentForm());
    setPending(remembered?.pending??null);
    if (remembered?.pending) {
      const data=remembered.pending.body.data;
      if (data) setForm(intentForm(data as Parameters<typeof intentForm>[0]));
    }
  },[storageKey,intents.data]);

  function remember(id:string, operation:NegotiationOperation|null) {
    try {
      if (storageKey) sessionStorage.setItem(storageKey,JSON.stringify({selected:id,pending:operation}));
    } catch { /* In-memory retry remains available if browser storage is disabled. */ }
  }
  function select(id:string) {
    setSelected(id);remember(id,null);setError("");setMessage("");
    const item=intents.data?.find(i=>i.id===id);
    setForm(item?intentForm(item.data.conditions):emptyIntentForm());
  }
  async function run(operation:NegotiationOperation) {
    if (busyRef.current) return;
    busyRef.current=true;setBusy(true);setError("");setMessage("");
    setPending(operation);remember(selectedId,operation);
    try {
      const result=await api<Resource|{intent:Resource;draft:Resource}>(operation.path,{method:operation.method,headers:{"Idempotency-Key":operation.idempotencyKey},body:JSON.stringify(operation.body)});
      const item="intent" in result?result.intent:result;
      setPending(null);setSelected(item.id);setForm(intentForm(item.data.conditions));remember(item.id,null);
      setMessage("intent" in result?"已生成计划草稿，请在下方校对确认后才会修改日程。":"本轮协商已保存，可继续修改同一意图。");
      await q.invalidateQueries();
      if ("intent" in result) onDraft?.(result.draft);
    } catch(e) {
      if (e instanceof ApiError && e.status>=400 && e.status<500) {
        setPending(null);remember(selectedId,null);
        if(e.status===409) await q.invalidateQueries();
      }
      setError(String(e));
    } finally {busyRef.current=false;setBusy(false);}
  }
  function save() {
    if (!settings.data || locked || !ready) return;
    try {
      const body:Record<string,unknown>={source_revision:settings.data.revision,data:intentConditions(form,settings.data.data.timezone)};
      if(current) body.revision=current.revision;
      void run(negotiationOperation(`/planning-intents${current?`/${current.id}`:""}`,current?"PATCH":"POST",body));
    } catch(e) {setError(String(e));}
  }
  function action(name:"preview"|"cancel"|"choose",optionId?:string) {
    if (!current || !settings.data || locked || !ready) return;
    void run(negotiationOperation(`/planning-intents/${current.id}/${name}`,"POST",{revision:current.revision,source_revision:settings.data.revision,...(optionId?{option_id:optionId}:{})}));
  }
  const changed=current && JSON.stringify(intentForm(current.data.conditions))!==JSON.stringify(form);
  const time=(v:string)=>new Date(v).toLocaleString("zh-CN",{timeZone:current?.data.conditions.timezone??settings.data?.data.timezone});

  return <section className="card" aria-label="多轮规划协商"><h3>一起调整计划</h3>
    <p>填写目标与取舍，逐轮修改同一意图。临时条件只用于本轮方案，选择后仍需校对计划草稿。描述中的模糊时间不会自动变成排程条件。</p>
    {(intents.error||settings.error||blocks.error||me.error||chosenDraft.error)&&<p role="alert">协商资料读取失败，请刷新后重试。</p>}
    <label>继续已有协商<select value={selectedId} disabled={locked||!ready} onChange={e=>select(e.target.value)}>
      <option value="new">新建协商</option>{intents.data?.map(i=><option value={i.id} key={i.id}>{i.data.conditions.description} · {i.data.status==="cancelled"?"已取消":i.data.status==="chosen"?"已选择草稿":"进行中"}</option>)}
    </select></label>
    <fieldset disabled={locked||!ready}><legend>本轮目标与明确条件</legend>
      <label>目标与取舍（不必填写私人原因）<textarea value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label>
      <div className="grid2"><label>开始日期<input type="date" value={form.target_date} onChange={e=>setForm({...form,target_date:e.target.value})}/></label>
      <label>范围天数<input type="number" min="1" max="7" value={form.horizon_days} onChange={e=>setForm({...form,horizon_days:e.target.value})}/></label>
      <label>本轮每日上限（分钟，可留空）<input type="number" min="0" max={settings.data?.data.daily_limit_minutes} value={form.reduced_daily_limit_minutes} onChange={e=>setForm({...form,reduced_daily_limit_minutes:e.target.value})}/></label></div>
      <p>设置时区：{settings.data?.data.timezone??"正在读取"}。留空沿用已确认上限；填写只能降低本轮负荷。</p>
      <Intervals title="临时保护时段" rows={form.protected_intervals} timezone={settings.data?.data.timezone??""} disabled={locked} onChange={rows=>setForm({...form,protected_intervals:rows})}/>
      <Intervals title="临时偏好时段" rows={form.preferred_intervals} timezone={settings.data?.data.timezone??""} disabled={locked} onChange={rows=>setForm({...form,preferred_intervals:rows})}/>
      <fieldset><legend>明确保留已有安排</legend>
        <p>锁定、已完成和未结束计时关联的安排自动保护。其他保留项需在本轮日期范围内。</p>
        {blocks.data?.map(b=><label key={b.id}><input type="checkbox" checked={form.keep_block_ids.includes(b.id)} onChange={e=>setForm({...form,keep_block_ids:e.target.checked?[...form.keep_block_ids,b.id]:form.keep_block_ids.filter(id=>id!==b.id)})}/>{b.data.title} · {time(b.data.starts_at)}</label>)}
        {!blocks.data?.length&&<p>当前没有已有安排。</p>}
      </fieldset>
      <Button type="button" onClick={save}>{current?"保存本轮修改并继续":"保存协商意图"}</Button>
    </fieldset>
    {current&&<div className="actions"><Button type="button" disabled={locked||!ready||!!changed||current.data.status!=="active"} onClick={()=>action("preview")}>预览可选方案</Button>
      <Button type="button" variant="outline" disabled={locked||!ready||current.data.status==="cancelled"} onClick={()=>action("cancel")}>取消本轮协商</Button>
      {changed&&<p>条件尚未保存，请先保存本轮修改。</p>}
    </div>}
    {pending&&<div><p>保存结果尚未确认；重试使用相同内容和操作键。</p><Button type="button" disabled={busy} onClick={()=>run(pending)}>重试本次协商操作</Button></div>}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {preview&&<div><p>{preview.explanation}</p>
      {preview.source_revision!==settings.data?.revision&&<p role="alert">事实版本已变化，请重新预览。原方案不可选择。</p>}
      {preview.conflicts.map((conflict:string,index:number)=><p key={index}>{conflict}</p>)}
      {preview.options.map((option:any)=><article className="card" key={option.id}><h4>{option.title}</h4>
        <p>新增安排 {option.proposed_minutes} 分钟 · 尚未安排 {option.unallocated_minutes} 分钟 · 偏好内 {option.preferred_minutes} 分钟 · 保留 {option.retained_count} 项</p>
        {option.risks.length>0?<ul>{option.risks.map((risk:any,index:number)=><li key={index}>{risk.title}：{risk.reason}；剩余 {risk.remaining_minutes??"未知"} 分钟</li>)}</ul>:<p>当前已知任务没有未安排风险；未知资料仍需自行校对。</p>}
        {option.explanation.map((line:string,index:number)=><p key={index}>{line}</p>)}
        <details><summary>比较安排与移动事项</summary><ul>{option.blocks.map((block:any)=><li key={block.id}>{block.title}：{time(block.starts_at)} — {time(block.ends_at)} · {option.changes.retained_ids.includes(block.id)?"保留":"新增"}</li>)}
        {option.removed_blocks.map((block:any)=><li key={`removed-${block.id}`}>{block.title}：将移除原建议 · {block.reason}</li>)}</ul></details>
        <Button type="button" disabled={locked||!ready||!!changed||current?.data.status!=="active"||preview.source_revision!==settings.data?.revision} onClick={()=>action("choose",option.id)}>选择{option.title}并生成草稿</Button>
      </article>)}
    </div>}
    {currentDraft&&(currentDraft.data.status==="pending"?<PlanReview draft={currentDraft}/>:<p>所选计划草稿：{currentDraft.data.status==="confirmed"?"已确认；继续修改或取消协商不会撤销该日程":"已取消或失效，请继续修改后重新预览"}</p>)}
  </section>;
}
