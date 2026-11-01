import {useRef,useState} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from './api';
import type {Resource} from './types';
import {DraftReview} from './DraftReview';
import {Button} from './components/ui/button';

export function ChatAssignmentReview({draft,disabled=false}:{draft:Resource;disabled?:boolean}){
 const q=useQueryClient(),lock=useRef(false),keys=useRef(new Map<string,string>());
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[expanded,setExpanded]=useState(false);
 const payload=draft.data.suggested_payload??draft.data.payload;
 const missing=payload.items.some((item:Record<string,unknown>)=>!item.due_at);
 const deferred=draft.data.source?.deadline_followup==='deferred';
 async function act(action:'save'|'defer'){
  if(lock.current||disabled)return;lock.current=true;setBusy(true);setError('');
  const identity=action+':'+draft.id+':'+draft.revision+':'+JSON.stringify(payload);let key=keys.current.get(identity);
  if(!key){key=crypto.randomUUID();keys.current.set(identity,key);}
  try{
   if(action==='defer')await api(`/agent/assignment-drafts/${draft.id}/defer-deadlines`,{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({revision:draft.revision})});
   else{
    const current=JSON.stringify(payload)===JSON.stringify(draft.data.payload)?draft:await api<Resource>(`/drafts/${draft.id}`,{method:'PUT',headers:{'Idempotency-Key':key+':edit'},body:JSON.stringify({revision:draft.revision,payload})});
    await api(`/drafts/${draft.id}/confirm`,{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({revision:current.revision})});
   }
   await q.invalidateQueries();
  }catch(e){setError(e instanceof ApiError&&e.status===409?'草稿已变化，已刷新。请重新核对后确认。':String(e));await q.invalidateQueries({queryKey:['drafts']});}
  finally{lock.current=false;setBusy(false);}
 }
 return <section className="chat-assignment-review" aria-label="对话作业草稿">
  <p className="chat-assignment-label">课间 · 作业草稿，尚未保存</p>
  <ol>{payload.items.map((item:Record<string,any>,i:number)=><li key={i}><span className="chat-assignment-number">{i+1}</span><div><h3>{item.title}</h3><p>{item.due_at?'截止 '+new Date(item.due_at).toLocaleString('zh-CN'):'未填写截止日期'}{!item.due_at&&item.due_text&&<span> · 原文：{item.due_text}</span>}</p></div></li>)}</ol>
  {missing&&<p>{deferred?'截止日期先留空，之后可以补充。':'这些作业分别什么时候截止？可以按编号回复，也可以暂不填写。'}</p>}
  {!expanded&&<div className="chat-assignment-actions">{missing&&!deferred&&<Button type="button" variant="outline" disabled={busy||disabled} onClick={()=>void act('defer')}>暂不填写</Button>}<Button type="button" disabled={busy||disabled} onClick={()=>void act('save')}>确认保存 {payload.items.length} 项</Button></div>}
  {error&&<p role="alert">{error}</p>}
  <details onToggle={e=>setExpanded(e.currentTarget.open)}><summary>校对详情</summary><div className="chat-assignment-images">{(payload.asset_ids?.length?payload.asset_ids:payload.asset_id?[payload.asset_id]:[]).map((id:string,i:number)=><img key={id} src={'/api/assets/'+id} alt={`作业原图 ${i+1}`}/>)}</div><DraftReview draft={draft}/></details>
 </section>;
}
