import {useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from './api';
import type {Resource} from './types';
import {Button} from './components/ui/button';

export const courseTypeLabels:Record<string,string>={unknown:'未知（未分类）',lecture:'讲授课',lab:'实验课',seminar:'研讨课',exam:'考试',other:'其他'};
const taskTypeLabels:Record<string,string>={unknown:'未知（未分类）',any:'通用任务',deep:'深度学习',review:'复习',exercise:'运动',other:'其他'};
const difficultyLabels:Record<string,string>={unknown:'未知（未设置）',low:'较轻',medium:'中等',high:'较难'};
type Entry={target:Resource;classification:Resource|null};
type Pending={path:string;body:Record<string,unknown>;key:string};

export function StudyTypes({targetId}:{targetId?:string}={}){
  const q=useQueryClient();
  const rows=useQuery({queryKey:['study-types'],queryFn:()=>api<{items:Entry[]}>('/study-types')});
  const [editor,setEditor]=useState<{entry:Entry;type:string;difficulty:string}|null>(null);
  const [pending,setPending]=useState<Pending|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const gate=useRef(false);
  async function send(operation?:Pending){
    if(gate.current)return;const request=pending??operation;if(!request)return;
    gate.current=true;setBusy(true);setPending(request);setError('');setMessage('');
    try{await api(request.path,{method:'PUT',headers:{'Idempotency-Key':request.key},body:JSON.stringify(request.body)});setPending(null);setEditor(null);setMessage('类型已保存，下一次规划和候选使用新依据。');await q.invalidateQueries();}
    catch(e){if(e instanceof ApiError&&e.status<500){setPending(null);if(e.status===409){setEditor(null);await q.invalidateQueries();}}setError(String(e));}
    finally{gate.current=false;setBusy(false);}
  }
  return <section className="card" aria-label="课程与任务类型"><h3>课程与任务类型</h3>
    <p>类型和难度由你明确设置。未知会保持未知；导入课表、执行补记和模型猜测不会自动给任务分类。课程类型用于明确的准备规则，任务类型用于匹配深度学习或复习偏好。</p>
    {rows.isPending&&<p>正在读取课程与任务…</p>}{rows.error&&<p role="alert">{String(rows.error)}</p>}
    {rows.data?.items.length===0&&<p>保存课程或任务后，可在这里设置类型。</p>}
    {rows.data?.items.filter(entry=>!targetId||entry.target.id===targetId).map(entry=>{const kind=entry.target.kind;const data=entry.classification?.data;const labels=kind==='course'?courseTypeLabels:taskTypeLabels;return <article className="step" key={entry.target.id} aria-label={`类型：${entry.target.data.name??entry.target.data.title}`}>
      <h4>{entry.target.data.name??entry.target.data.title}</h4><p>{kind==='course'?'课程':'任务'} · {labels[data?.[kind==='course'?'course_type':'task_type']??'unknown']}{kind==='task'?` · 难度：${difficultyLabels[data?.difficulty??'unknown']}`:''}</p>
      <Button type="button" variant="outline" disabled={busy||!!pending||!!editor} onClick={()=>setEditor({entry,type:data?.[kind==='course'?'course_type':'task_type']??'unknown',difficulty:data?.difficulty??'unknown'})}>设置类型</Button>
    </article>;})}
    {editor&&<form onSubmit={e=>{e.preventDefault();const target=editor.entry.target;void send({path:`/study-types/${target.kind}/${target.id}`,body:{revision:editor.entry.classification?.revision??0,target_revision:target.revision,...(target.kind==='course'?{course_type:editor.type}:{task_type:editor.type,difficulty:editor.difficulty})},key:crypto.randomUUID()});}}><fieldset disabled={busy||!!pending}>
      <legend>{editor.entry.target.data.name??editor.entry.target.data.title} · 明确分类</legend>
      <label>明确类型<select aria-label="明确类型" value={editor.type} onChange={e=>setEditor({...editor,type:e.target.value})}>{Object.entries(editor.entry.target.kind==='course'?courseTypeLabels:taskTypeLabels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>
      {editor.entry.target.kind==='task'&&<label>明确难度<select aria-label="明确难度" value={editor.difficulty} onChange={e=>setEditor({...editor,difficulty:e.target.value})}>{Object.entries(difficultyLabels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>}
      <Button type="submit">确认保存类型</Button><Button type="button" variant="outline" onClick={()=>setEditor(null)}>取消分类编辑</Button>
    </fieldset></form>}
    {pending&&!busy&&<Button type="button" onClick={()=>void send()}>重试同一次类型保存</Button>}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  </section>;
}
