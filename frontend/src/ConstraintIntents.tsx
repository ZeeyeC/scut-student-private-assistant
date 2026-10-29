import {useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from './api';
import type {Resource} from './types';
import {Button} from './components/ui/button';
import {ConstraintReview} from './SchedulingConstraints';
import {constraintIntentForm,constraintIntentChanges,newConstraintIntentOperation,type ConstraintIntentForm} from './constraint-intent-state';

type View=Resource&{draft:Resource|null;constraint:Resource|null};
type Operation=ReturnType<typeof newConstraintIntentOperation<Record<string,unknown>>>;
const labels:Record<string,string>={clarifying:'待补充时间',ready_for_review:'待校对确认',confirmed:'规则已确认',disabled:'规则已停用',cancelled:'意图已取消'};

export function ConstraintIntents({threadId}:{threadId?:string}){
  const q=useQueryClient();
  const rows=useQuery({queryKey:['constraint-intents'],queryFn:()=>api<View[]>('/constraint-intents')});
  const [editor,setEditor]=useState<{row?:View;form:ConstraintIntentForm}|null>(null);
  const [pending,setPending]=useState<Operation|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const gate=useRef(false);const locked=busy||!!pending;
  async function send(op?:Operation){
    if(gate.current)return;
    const request=pending??op;if(!request)return;
    gate.current=true;setBusy(true);setPending(request);setError('');
    try{
      await api(request.path,{method:request.method,headers:{'Idempotency-Key':request.idempotencyKey},body:JSON.stringify(request.body)});
      setPending(null);setEditor(null);await q.invalidateQueries();
    }catch(e){
      if(e instanceof ApiError&&e.status<500){setPending(null);await q.invalidateQueries({queryKey:['constraint-intents']});}
      setError(String(e));
    }finally{gate.current=false;setBusy(false);}
  }
  function save(){
    if(!editor)return;
    const fields=constraintIntentChanges(editor.form);
    void send(editor.row?newConstraintIntentOperation(`/constraint-intents/${editor.row.id}`,'PATCH',{revision:editor.row.revision,changes:fields}):newConstraintIntentOperation('/constraint-intents','POST',{data:fields,thread_id:threadId||null}));
  }
  function change(p:Partial<ConstraintIntentForm>){if(editor)setEditor({...editor,form:{...editor.form,...p}});}
  return <section aria-label="对话约束意图">
    <h3>持续约束与禁排</h3>
    <p>缺少钟点先补充，同一意图继续修改；生成草稿不保存正式规则。无需记录医院等私人事由，正式名称默认“不可安排”。</p>
    <Button type="button" variant="outline" disabled={locked||!!editor} onClick={()=>setEditor({form:constraintIntentForm()})}>新建禁排意图</Button>
    {rows.isPending&&<p>正在读取约束意图…</p>}{rows.error&&<p role="alert">{String(rows.error)}</p>}
    {rows.data?.map(row=><article className="card" key={row.id} aria-label={`约束意图 ${row.data.fields.day_expression??'日期待确认'}`}>
      <h4>{labels[row.data.status]??'待核对'} · {row.data.fields.day_expression??'日期未知'}</h4>
      <p>{row.data.fields.start_time??'开始未知'} 至 {row.data.fields.end_day_offset?'次日 ':''}{row.data.fields.end_time??'结束未知'} · {row.data.fields.timezone} · {row.data.fields.recurrence==='weekly'?'每周重复':'单次'}</p>
      <p>按消息日期 {row.data.reference_date} 定位；记录日期不会随刷新偷偷滚到下周。</p>
      {row.data.clarifications?.map((v:string)=><p role="status" key={v}>{v}</p>)}
      {['clarifying','ready_for_review'].includes(row.data.status)&&<>
        <Button type="button" variant="outline" disabled={locked||!!editor} onClick={()=>setEditor({row,form:constraintIntentForm(row)})}>补充或修改时间</Button>
        <Button type="button" disabled={locked||!!row.data.clarifications?.length} onClick={()=>send(newConstraintIntentOperation(`/constraint-intents/${row.id}/prepare`,'POST',{revision:row.revision}))}>生成同一约束草稿</Button>
        <Button type="button" variant="outline" disabled={locked} onClick={()=>send(newConstraintIntentOperation(`/constraint-intents/${row.id}/cancel`,'POST',{revision:row.revision}))}>取消此意图</Button>
      </>}
      {row.draft?.data.status==='pending'&&<ConstraintReview draft={row.draft} key={row.draft.id+':'+row.draft.revision}/>}
      {row.constraint?.data.active&&<>
        {!row.data.deactivation_requested?<Button type="button" variant="outline" disabled={locked} onClick={()=>send(newConstraintIntentOperation(`/constraint-intents/${row.id}/cancel`,'POST',{revision:row.revision}))}>请求停用已确认规则</Button>:<>
          <p>停用后新规划可重新使用该时段，已保存日程和历史记录保留。</p>
          <Button type="button" disabled={locked} onClick={()=>send(newConstraintIntentOperation(`/scheduling-constraints/${row.constraint!.id}`,'PATCH',{revision:row.constraint!.revision,active:false}))}>确认停用这条规则</Button>
        </>}
      </>}
    </article>)}
    {editor&&<form onSubmit={e=>{e.preventDefault();save();}}><fieldset disabled={locked}>
      <legend>{editor.row?'补充原意图':'新的约束意图'}</legend>
      <label>日期或相对星期<input value={editor.form.day_expression} placeholder="这周三、下周五或2026-11-04" onChange={e=>change({day_expression:e.target.value})}/></label>
      <div className="grid2"><label>约束开始钟点<input type="time" value={editor.form.start_time} onChange={e=>change({start_time:e.target.value})}/></label><label>约束结束钟点<input type="time" value={editor.form.end_time} onChange={e=>change({end_time:e.target.value})}/></label></div>
      <label><input type="checkbox" checked={editor.form.end_day_offset===1} onChange={e=>change({end_day_offset:e.target.checked?1:0})}/>明确次日结束</label>
      <label>约束重复方式<select value={editor.form.recurrence} onChange={e=>change({recurrence:e.target.value as 'once'|'weekly'})}><option value="once">单次</option><option value="weekly">每周</option></select></label>
      {editor.form.recurrence==='weekly'&&<><div>{['一','二','三','四','五','六','日'].map((name,i)=><label key={name}><input type="checkbox" checked={editor.form.weekdays.includes(i+1)} onChange={e=>change({weekdays:e.target.checked?[...editor.form.weekdays,i+1]:editor.form.weekdays.filter(x=>x!==i+1)})}/>星期{name}</label>)}</div><label>约束有效截止（可空）<input type="date" value={editor.form.valid_until} onChange={e=>change({valid_until:e.target.value})}/></label></>}
      <label>规则性质<select value={editor.form.strength} onChange={e=>change({strength:e.target.value as 'hard'|'soft'})}><option value="hard">不可安排</option><option value="soft">优先学习，可让步</option></select></label>
      <label>约束IANA时区（空白使用学习设置）<input value={editor.form.timezone} onChange={e=>change({timezone:e.target.value})}/></label>
      <Button type="submit">保存候选时间</Button><Button type="button" variant="outline" onClick={()=>setEditor(null)}>取消编辑</Button>
    </fieldset></form>}
    {pending&&!busy&&<><p>结果尚未确认，重试沿用原操作。</p><Button type="button" onClick={()=>send()}>重试约束操作</Button></>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
