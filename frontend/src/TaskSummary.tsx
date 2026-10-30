import {useRef,useState} from 'react';
import {useQueries,useQueryClient} from '@tanstack/react-query';
import type {Resource} from './types';
import {api,ApiError} from './api';

export function useTaskEstimates(tasks:Resource[]){
  const results=useQueries({queries:tasks.map(task=>({queryKey:['steps',task.id],queryFn:()=>api<Resource[]>(`/tasks/${task.id}/steps`)}))});
  return new Map(tasks.map((task,i)=>{
    const steps=results[i].data;
    return [task.id,steps?.length&&steps.every(step=>Number.isFinite(step.data.estimated_minutes))?steps.reduce((sum,s)=>sum+s.data.estimated_minutes,0):null];
  }));
}
export function useTaskCompletion(task:Resource){
  const q=useQueryClient(),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const gate=useRef(false),pending=useRef<{key:string;body:object}|null>(null);
  async function toggle(){
    if(gate.current)return;gate.current=true;setBusy(true);setError('');
    const operation=pending.current??{key:crypto.randomUUID(),body:{revision:task.revision,status:task.data.status==='completed'?'open':'completed'}};
    pending.current=operation;
    try{await api(`/tasks/${task.id}`,{method:'PATCH',headers:{'Idempotency-Key':operation.key},body:JSON.stringify(operation.body)});pending.current=null;await q.invalidateQueries();}
    catch(e){if(e instanceof ApiError&&e.status<500){pending.current=null;await q.invalidateQueries({queryKey:['tasks']});}setError(String(e));}
    finally{gate.current=false;setBusy(false);}
  }
  return {busy,error,toggle};
}
export function taskCourse(task:Resource,courses:Resource[]){return courses.find(c=>c.id===task.data.course_id)?.data.name??'未分类';}
export function dueLabel(value:unknown,timezone:string,now=new Date()){
  if(typeof value!=='string'||!Number.isFinite(Date.parse(value)))return '截止待确认';
  const date=new Date(value),day=(d:Date)=>d.toLocaleDateString('en-CA',{timeZone:timezone});
  const delta=Math.round((Date.parse(day(date))-Date.parse(day(now)))/86400000);
  const time=date.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:timezone});
  if(delta===0||delta===1)return (delta===0?'今天':'明天')+(time==='23:59'?'':' '+time);
  if(delta>1&&delta<7)return date.toLocaleDateString('zh-CN',{weekday:'short',timeZone:timezone});
  return date.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric',timeZone:timezone});
}
export function TaskSummaryRow({task,course,minutes,timezone,table=false,onOpen}:{task:Resource;course:string;minutes:number|null;timezone:string;table?:boolean;onOpen:()=>void}){
  const completion=useTaskCompletion(task);
  return <div className={`task-list-row summary-task-row${task.data.status==='completed'?' task-completed':''}`}>
    <input type="checkbox" aria-label={`完成${task.data.title}`} checked={task.data.status==='completed'} disabled={completion.busy||task.data.status==='archived'} onChange={()=>void completion.toggle()}/>
    <div className="summary-task-content"><button type="button" className="summary-task-title" onClick={onOpen}>{task.data.title}</button><small>{course}{!table&&`　${dueLabel(task.data.due_at,timezone)}`}</small>{completion.error&&<p role="alert">{completion.error}</p>}</div>
    <div className="summary-task-time">{table&&<span>{dueLabel(task.data.due_at,timezone)}</span>}<span>{minutes===null?'待估时':`${minutes} 分钟`}</span></div>
  </div>;
}
