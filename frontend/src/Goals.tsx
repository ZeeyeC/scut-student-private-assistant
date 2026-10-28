import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './api';
import { Button } from './components/ui/button';
import { goalForm, goalPayload, goalOperation, type GoalForm, type GoalOperation, type GoalsView, type GoalView } from './goal-state';

const loadLabels = {study:'学习',exercise:'运动',other:'其他'};
const adjustmentLabels = {reduce:'允许减少投入',delay:'允许推迟',ask:'先征求我同意'};
type Task = {id:string;data:{title:string;status?:string}};

export function Goals() {
  const q = useQueryClient();
  const goals = useQuery({queryKey:['goals'], queryFn:()=>api<GoalsView>('/goals')});
  const tasks = useQuery({queryKey:['tasks'], queryFn:()=>api<Task[]>('/tasks')});
  const [editor,setEditor] = useState<{id?:string;revision:number;form:GoalForm}|null>(null);
  const [pending,setPending] = useState<GoalOperation|null>(null);
  const [busy,setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error,setError] = useState('');
  const [message,setMessage] = useState('');
  const locked = busy || !!pending;
  function change(values:Partial<GoalForm>) { if (editor) setEditor({...editor,form:{...editor.form,...values}}); }
  function subtask(index:number, values:Partial<GoalForm['subtasks'][number]>) {
    if (editor) change({subtasks:editor.form.subtasks.map((s,i)=>i===index?{...s,...values}:s)});
  }
  async function save(operation?:GoalOperation) {
    if (busyRef.current) return;
    setError('');setMessage('');
    let request = pending ?? operation;
    if (!request && editor) {
      try { request = goalOperation(editor.id?`/goals/${editor.id}`:'/goals',editor.id?'PATCH':'POST',goalPayload(editor.revision,editor.form)); }
      catch(e) { setError(String(e));return; }
    }
    if (!request) return;
    setPending(request);busyRef.current=true;setBusy(true);
    try {
      await api<GoalView>(request.path,{method:request.method,headers:{'Idempotency-Key':request.idempotencyKey},body:JSON.stringify(request.body)});
      setPending(null);setEditor(null);setMessage('用户确认的目标已保存。容量与排程联动待接入。');
      await q.invalidateQueries();
    } catch(e) {
      if (e instanceof ApiError && e.status>=400 && e.status<500) {
        setPending(null);
        if (e.status===409) {setEditor(null);await q.invalidateQueries({queryKey:['goals']});}
      }
      setError(String(e));
    } finally {busyRef.current=false;setBusy(false);}
  }
  function toggle(goal:GoalView) {void save(goalOperation(`/goals/${goal.id}`,'PATCH',{revision:goal.revision,paused:!goal.data.paused}));}
  return <section aria-label="长期目标">
    <h3>长期目标</h3>
    <p>容量未知 · 尚未完成可用时间核对。这里先记录每周预算，保存目标不会自动新增任务或安排。</p>
    {goals.isPending && <p role="status">正在读取目标…</p>}
    {goals.error && <><p role="alert">读取目标失败：{String(goals.error)}</p><Button type="button" variant="outline" onClick={()=>goals.refetch()}>重试读取目标</Button></>}
    {goals.data && <>
      {!editor && <Button type="button" variant="outline" disabled={locked} onClick={()=>{setEditor({revision:0,form:goalForm()});setMessage('');setError('');}}>新建目标</Button>}
      {!goals.data.goals.length && <p>尚未设置目标。确认保存后才会记录。</p>}
      {goals.data.goals.map(goal=><article key={goal.id} aria-label={`目标：${goal.data.title}`}>
        <h4>{goal.data.title} · {goal.data.paused?'已暂停':'进行中'}</h4>
        <p>用户设置 · 已确认 · 版本 {goal.revision}</p>
        <p>{goal.data.description || '未填写说明'}</p>
        <p>截止：{goal.data.deadline ?? '未知（未设置）'} · 每周预算：{goal.data.weekly_budget_minutes} 分钟 · 优先级：{goal.data.priority} · {loadLabels[goal.data.load_category]} · {adjustmentLabels[goal.data.allowed_adjustment]}</p>
        {goal.data.paused && <p>暂停期间不生成目标安排；已有任务与完成事实保留。</p>}
        <ul>{goal.data.subtasks.map(s=><li key={s.id}>{s.title} · {s.status==='completed'?'已完成':'待完成'} · 预计 {s.estimated_minutes} 分钟{ s.task_id && (()=>{const ref=goal.references.find(r=>r.subtask_id===s.id);return <span> · 关联任务：{ref?.available?ref.title:'已不可用'}（{s.task_id}）</span>;})()}</li>)}</ul>
        <details><summary>已完成事实（{goal.data.completion_history.length}）</summary><ul>{goal.data.completion_history.map((fact,i)=><li key={i}>{fact.title} · {fact.estimated_minutes} 分钟 · {fact.completed_at}</li>)}</ul></details>
        <Button type="button" variant="outline" disabled={locked || !!editor || goals.isFetching} onClick={()=>{setEditor({id:goal.id,revision:goal.revision,form:goalForm(goal)});setError('');setMessage('');}}>编辑目标</Button>
        <Button type="button" variant="outline" disabled={locked || !!editor || goals.isFetching} onClick={()=>toggle(goal)}>{goal.data.paused?'恢复目标':'暂停目标'}</Button>
      </article>)}
    </>}
    {editor && <form onSubmit={e=>{e.preventDefault();void save();}}>
      <fieldset disabled={locked}><legend>{editor.id?'编辑目标':'新建目标'}</legend>
        <label>目标名称<input maxLength={200} required value={editor.form.title} onChange={e=>change({title:e.target.value})}/></label>
        <label>说明<textarea maxLength={4000} value={editor.form.description} onChange={e=>change({description:e.target.value})}/></label>
        <label>截止时间（未知可留空，需带时区）<input placeholder="2026-12-01T18:00:00+08:00" value={editor.form.deadline} onChange={e=>change({deadline:e.target.value})}/></label>
        <label>每周预算（整数分钟，0 表示本周不投入）<input type="number" min={0} max={10080} step={1} required value={editor.form.weekly_budget_minutes} onChange={e=>change({weekly_budget_minutes:e.target.value})}/></label>
        <label>优先级<select value={editor.form.priority} onChange={e=>change({priority:Number(e.target.value)})}><option value={1}>低</option><option value={2}>普通</option><option value={3}>高</option></select></label>
        <label>负荷类别<select value={editor.form.load_category} onChange={e=>change({load_category:e.target.value as GoalForm['load_category']})}>{Object.entries(loadLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label>允许的调整<select value={editor.form.allowed_adjustment} onChange={e=>change({allowed_adjustment:e.target.value as GoalForm['allowed_adjustment']})}>{Object.entries(adjustmentLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <p>子任务由你确认；关联仅引用现有任务。移除子任务或修改状态不会清除已完成事实。</p>
        {tasks.error && <p role="alert">关联任务读取失败：{String(tasks.error)}</p>}
        {editor.form.subtasks.map((s,i)=><fieldset key={s.id??`new-${i}`}><legend>子任务 {i+1}</legend>
          <label>子任务名称<input required maxLength={200} value={s.title} onChange={e=>subtask(i,{title:e.target.value})}/></label>
          <label>预计分钟<input type="number" min={0} max={100000} step={1} required value={s.estimated_minutes} onChange={e=>subtask(i,{estimated_minutes:e.target.value})}/></label>
          <label>状态<select value={s.status} onChange={e=>subtask(i,{status:e.target.value as 'open'|'completed'})}><option value="open">待完成</option><option value="completed">已完成</option></select></label>
          <label>关联现有任务（可选）<select value={s.task_id} onChange={e=>subtask(i,{task_id:e.target.value})}><option value="">不关联</option>{s.task_id&&!tasks.data?.some(t=>t.id===s.task_id)&&<option value={s.task_id}>现有关联：{s.task_id}</option>}{tasks.data?.map(t=><option key={t.id} value={t.id}>{t.data.title}</option>)}</select></label>
          <Button type="button" variant="outline" onClick={()=>change({subtasks:editor.form.subtasks.filter((_,j)=>i!==j)})}>移除子任务</Button>
        </fieldset>)}
        <Button type="button" variant="outline" onClick={()=>change({subtasks:[...editor.form.subtasks,{title:'',status:'open',estimated_minutes:'',task_id:''}]})}>添加子任务</Button>
        <Button type="submit" variant="outline">确认并保存目标</Button>
        <Button type="button" variant="outline" onClick={()=>{setEditor(null);setError('');}}>取消编辑</Button>
      </fieldset>
    </form>}
    {pending && <p role="status">{busy?'正在保存目标…':'保存结果尚未确认；重试使用同一请求，避免重复写入。'}</p>}
    {pending&&!busy&&<Button type="button" variant="outline" onClick={()=>save()}>重试同一次保存</Button>}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  </section>;
}
export default Goals;
