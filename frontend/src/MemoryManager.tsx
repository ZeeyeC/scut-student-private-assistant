import {useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from './api';
import type {Resource} from './types';
import {Button} from './components/ui/button';
import './memory.css';

type MemoryView={settings:Resource;memories:Resource[];candidates:Resource[]};
export function useMemoryView(){return useQuery({queryKey:['memories'],queryFn:()=>api<MemoryView>('/memories')});}
function useMutation(){
  const q=useQueryClient(),lock=useRef(false),keys=useRef(new Map<string,string>());
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function act(path:string,body:unknown,method='POST'){
    if(lock.current)return false;
    lock.current=true;setBusy(true);setError('');
    const fingerprint=path+JSON.stringify(body);let key=keys.current.get(fingerprint);
    if(!key){key=crypto.randomUUID();keys.current.set(fingerprint,key);}
    try{await api(path,{method,headers:{'Idempotency-Key':key},body:JSON.stringify(body)});await Promise.all([q.invalidateQueries({queryKey:['memories']}),q.invalidateQueries({queryKey:['profile']}),q.invalidateQueries({queryKey:['planning']})]);return true;}
    catch(e){setError(String(e));if(e instanceof ApiError&&e.status===409)await q.invalidateQueries({queryKey:['memories']});return false;}
    finally{lock.current=false;setBusy(false);}
  }
  return {act,busy,error};
}
const labels:Record<string,string>={focus_minutes:'专注时长',break_minutes:'休息时长',daily_load_minutes:'每日学习上限'};
function time(value:string|undefined){return value?new Date(value).toLocaleString('zh-CN'):'长期有效';}
function Source({data}:{data:Resource['data']}){return <p className="muted memory-meta">{data.source?.kind==='chat'?'来自对话':'手动填写'} · {time(data.confirmed_at??data.created_at)}{data.expires_at&&<> · 有效至 {time(data.expires_at)}</>}</p>;}
export function PendingMemories({threadId,disabled=false}:{threadId?:string;disabled?:boolean}){
  const view=useMemoryView(),profile=useQuery({queryKey:['profile'],queryFn:()=>api<Resource>('/profile')}),m=useMutation();
  const pending=view.data?.candidates.filter(c=>!threadId||c.data.source?.thread_id===threadId)??[];
  return <section aria-label="待确认记忆" className="memory-pending">
    {disabled&&pending.length>0&&<p className="muted">请等待助手本轮结束后确认。</p>}
    {view.error&&<p role="alert">{String(view.error)}</p>}
    {!view.isPending&&!pending.length&&<p className="muted">暂无待确认记忆。</p>}
    {pending.map(c=>{const d=c.data,old=view.data?.memories.find(r=>r.data.key===d.key&&r.data.status!=='forgotten');return <article className="memory-review" key={c.id}>
      <h3>{d.action==='forget'?'遗忘记忆':'记忆待确认'} · {labels[d.key]??d.key}</h3>
      {old&&<p>当前：{old.data.content}</p>}
      {d.action==='upsert'&&<p>新内容：{d.content}</p>}
      {d.profile_field&&<p>同步学习偏好：{labels[d.profile_field]} {profile.data?.data.preferences[d.profile_field]??'未设置'} → {d.action==='forget'?'清除仍匹配的值':`${d.profile_value} 分钟`}</p>}
      <Source data={d}/>
      {d.action==='forget'&&<p className="muted">清除这项记忆及候选版本，保留之后手动改过的学习偏好。聊天记录和备份仍保留。</p>}
      <div className="memory-actions">{[['confirm',d.action==='forget'?'确认遗忘':'确认记忆'],['reject',d.action==='forget'?'取消':'拒绝'],['refresh','重新校对']].map(([action,label])=><Button key={action} type="button" variant={action==='confirm'?'default':'outline'} disabled={m.busy||disabled} onClick={()=>void m.act(`/memories/candidates/${c.id}/${action}`,{revision:c.revision})}>{label}</Button>)}</div>
    </article>;})}
    {m.error&&<p role="alert">{m.error}</p>}
  </section>;
}
function MemoryForm({memory,onDone}:{memory?:Resource;onDone:()=>void}){
  const m=useMutation(),[key,setKey]=useState(memory?.data.key??''),[content,setContent]=useState(memory?.data.content??''),[category,setCategory]=useState(memory?.data.category??'interaction_preference'),[field,setField]=useState(memory?.data.profile_field??''),[value,setValue]=useState(String(memory?.data.profile_value??'')),[expiry,setExpiry]=useState(memory?.data.expires_at?new Date(new Date(memory.data.expires_at).getTime()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16):'');
  return <form className="memory-form" onSubmit={async e=>{e.preventDefault();const body={key:field||key,content,category:field?'study_preference':category,expires_at:!field&&expiry?new Date(expiry).toISOString():null,profile_field:field||null,profile_value:field?Number(value):null};if(await m.act('/memories/candidates',body))onDone();}}>
    <label>记忆主题<input required maxLength={80} value={key} disabled={!!memory||!!field} onChange={e=>setKey(e.target.value)}/></label>
    <label>内容<textarea aria-label="内容" required maxLength={400} value={content} onChange={e=>setContent(e.target.value)}/></label>
    <label>类型<select value={category} disabled={!!field} onChange={e=>setCategory(e.target.value)}><option value="interaction_preference">交互偏好</option><option value="study_preference">学习偏好</option></select></label>
    <label>同步永久学习偏好<select value={field} disabled={!!memory} onChange={e=>setField(e.target.value)}><option value="">不关联设置</option>{Object.entries(labels).map(([k,label])=><option value={k} key={k}>{label}</option>)}</select></label>
    {field?<label>时长（分钟）<input type="number" required min={field==='focus_minutes'?5:0} max={field==='focus_minutes'?240:field==='break_minutes'?120:720} value={value} onChange={e=>setValue(e.target.value)}/></label>:<label>有效至（本机时间，留空为长期）<input type="datetime-local" value={expiry} onChange={e=>setExpiry(e.target.value)}/></label>}
    <p className="muted">提交后仍需确认才会生效。请勿填写密码、密钥、联系方式或身份号码。</p>
    <div className="memory-actions"><Button disabled={m.busy}>提出记忆候选</Button><Button type="button" variant="outline" onClick={onDone}>取消</Button></div>
    {m.error&&<p role="alert">{m.error}</p>}
  </form>;
}
export function MemoryManager(){
  const view=useMemoryView(),m=useMutation(),[editing,setEditing]=useState<Resource|null|undefined>(undefined),[pendingFlags,setPendingFlags]=useState<Record<string,boolean>|null>(null);
  const active=view.data?.memories.filter(r=>r.data.status==='active')??[],inactive=view.data?.memories.filter(r=>['expired','superseded'].includes(r.data.status))??[];
  const s=view.data?.settings;
  return <section className="card memory-manager" aria-label="记忆与偏好">
    <h2>记忆与偏好</h2><p className="muted">记忆保存在本机，相关内容在使用助手时可能发送给你配置的模型。仅确认后的偏好参与召回；永久学习偏好同步到个人设置。</p>
    {view.error&&<p role="alert">{String(view.error)}</p>}
    {s&&<div className="memory-options">{[['recall_enabled','使用已确认记忆'],['suggestions_enabled','允许助手提出记忆建议']].map(([k,label])=><label key={k}><input type="checkbox" checked={!!(pendingFlags?.[k]??s.data[k])} disabled={m.busy} onChange={e=>{const value=e.target.checked;setPendingFlags({...s.data,[k]:value});void m.act('/memories/preferences',{revision:s.revision,recall_enabled:s.data.recall_enabled,suggestions_enabled:s.data.suggestions_enabled,[k]:value},'PUT').finally(()=>setPendingFlags(null));}}/>{label}</label>)}</div>}
    <h3>已确认 · {active.length}</h3>{!active.length&&<p className="muted">还没有已确认记忆。</p>}
    {active.map(r=><article className="memory-row" key={r.id}><h4>{labels[r.data.key]??r.data.key}</h4><p>{r.data.content}</p><Source data={r.data}/><div className="memory-actions"><Button variant="outline" type="button" onClick={()=>setEditing(r)}>修改</Button><Button variant="outline" type="button" disabled={m.busy} onClick={()=>void m.act(`/memories/${r.id}/forget`,{revision:r.revision})}>遗忘</Button></div></article>)}
    {editing!==undefined?<MemoryForm key={editing?.id??'new'} memory={editing??undefined} onDone={()=>setEditing(undefined)}/>:<Button type="button" variant="outline" onClick={()=>setEditing(null)}>添加记忆</Button>}
    <h3>待确认</h3><PendingMemories/>
    {!!inactive.length&&<details><summary>已过期或被手动设置替代 · {inactive.length}</summary>{inactive.map(r=><article className="memory-row" key={r.id}><p>{r.data.content} · {r.data.status==='expired'?'已过期':'已由手动设置替代'}</p><Button type="button" variant="outline" disabled={m.busy} onClick={()=>void m.act(`/memories/${r.id}/forget`,{revision:r.revision})}>遗忘</Button></article>)}</details>}
    <p className="muted">遗忘后，后续对话不再从记忆和旧模型上下文取回该内容。已有聊天记录与备份仍保留。关闭召回不会清除已同步的学习设置。</p>
    <Button type="button" variant="destructive" disabled={!s||m.busy} onClick={()=>{if(s&&window.confirm('清空所有记忆和候选？仍匹配的学习偏好会被清除，后续手动修改、聊天记录和备份保留。'))void m.act('/memories/clear',{revision:s.revision,confirm:true});}}>清空记忆</Button>
    {m.error&&<p role="alert">{m.error}</p>}
  </section>;
}
