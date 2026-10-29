import { useRef,useState } from 'react';
import { useQuery,useQueryClient } from '@tanstack/react-query';
import { api,ApiError } from './api';
import { Button } from './components/ui/button';
import { durationActions,durationOperation,type DurationAction,type DurationOperation,type DurationSuggestion,type DurationSuggestionList } from './duration-suggestions-state';

const stateLabels={pending:'待确认',accepted:'已接受',rejected:'已拒绝',restored:'已恢复默认'};
const feedbackLabels={partial:'部分执行',completed:'完成反馈',not_started:'未开始',skipped:'跳过'};
const minutes=(value:number|null)=>value===null?'未知（未设置）':`${value} 分钟`;

export function DurationSuggestions() {
  const q=useQueryClient();
  const list=useQuery({queryKey:['duration-suggestions'],queryFn:()=>api<DurationSuggestionList>('/duration-suggestions')});
  const [pending,setPending]=useState<DurationOperation|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const pendingRef=useRef<DurationOperation|null>(null),busyRef=useRef(false);
  async function run(operation?:DurationOperation,retry=false) {
    if(busyRef.current||(pendingRef.current&&!retry))return;
    const request=pendingRef.current??operation;if(!request)return;
    pendingRef.current=request;setPending(request);busyRef.current=true;setBusy(true);setError('');setMessage('');
    try {
      await api(request.path,{method:request.method,headers:{'Idempotency-Key':request.idempotencyKey},body:JSON.stringify(request.body)});
      pendingRef.current=null;setPending(null);
      setMessage(request.body.action==='accept'?'已接受时长建议并更新关联步骤的预计分钟。':request.body.action==='reject'?'已拒绝建议，步骤预计时长保持不变。':'已恢复生成建议前的预计时长；原值未知时恢复为未知。');
      await q.invalidateQueries();
    }catch(e){
      if(e instanceof ApiError&&e.status>=400&&e.status<500){pendingRef.current=null;setPending(null);if(e.status===409)await q.invalidateQueries({queryKey:['duration-suggestions']});}
      setError(String(e));
    }finally{busyRef.current=false;setBusy(false);}
  }
  function act(item:DurationSuggestion,action:DurationAction) {
    try{void run(durationOperation(item,action));}catch(e){setError(String(e));}
  }
  const locked=busy||!!pending;
  return <section aria-label="时长建议"><h3>步骤时长建议</h3>
    <p>未接入生成服务。这里仅消费已保存且符合契约的真实建议；不会根据计划分钟伪造实际耗时或学习样本。</p>
    {list.isPending&&<p role="status">正在读取时长建议…</p>}
    {list.error&&<p role="alert">读取时长建议失败：{String(list.error)}</p>}
    <Button type="button" variant="outline" disabled={locked||list.isFetching} onClick={()=>void list.refetch()}>刷新时长建议</Button>
    {list.data&&<>
      {!list.data.suggestions.length&&<p>暂无可消费的有效时长建议。建议生成算法仍待接入。</p>}
      {list.data.invalid_suggestion_count>0&&<p role="alert">有 {list.data.invalid_suggestion_count} 条记录不符合消费契约，已阻止展示和应用；需要生成端修复。</p>}
      {list.data.suggestions.map(item=>{
        const actions=durationActions(item);
        return <article key={item.id} className="card" aria-label={`时长建议：${item.step_title??'关联步骤不可用'}`}>
          <h4>{item.task_title??'关联任务不可用'} · {item.step_title??'关联步骤不可用'}</h4>
          <p>{stateLabels[item.data.state]} · 当前预计：{minutes(item.current_estimated_minutes)} · 建议：{minutes(item.data.suggested_minutes)} · 原默认：{minutes(item.data.default_estimated_minutes)}</p>
          <ul>{item.data.reasons.map((reason,index)=><li key={index}>{reason}</li>)}</ul>
          <details><summary>样本依据（{item.data.sample_basis.length} 条已保存执行记录）</summary>
            <ul>{item.data.sample_basis.map(sample=><li key={sample.execution_id}>执行记录 {sample.execution_id} · 版本 {sample.execution_revision} · 实际 {sample.actual_minutes} 分钟 · {feedbackLabels[sample.feedback]}</li>)}</ul>
            <p>任务 {item.data.task_id} · 生成时任务版本 {item.data.task_revision} · 步骤 {item.data.step_id} · 生成时步骤版本 {item.data.step_revision} · 资料版本 {item.data.source_revision}</p>
          </details>
          {item.freshness==='stale'&&<p role="alert">建议依据已变化：{item.freshness_reason}。请等待基于最新资料的建议，当前无法应用或恢复。</p>}
          {actions.includes('accept')&&<Button type="button" variant="outline" disabled={locked||list.isFetching} onClick={()=>act(item,'accept')}>接受此时长</Button>}
          {actions.includes('reject')&&<Button type="button" variant="outline" disabled={locked||list.isFetching} onClick={()=>act(item,'reject')}>拒绝此建议</Button>}
          {actions.includes('restore_default')&&<Button type="button" variant="outline" disabled={locked||list.isFetching} onClick={()=>act(item,'restore_default')}>恢复原默认时长</Button>}
        </article>;
      })}
    </>}
    {pending&&<p role="status">{busy?'正在处理时长选择…':'结果尚未确认；重试将保留原建议、版本和请求标识。'}</p>}
    {pending&&!busy&&<Button type="button" variant="outline" onClick={()=>void run(undefined,true)}>重试同一次时长操作</Button>}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  </section>;
}
export default DurationSuggestions;
