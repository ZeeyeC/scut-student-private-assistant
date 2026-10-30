import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {TaskCard} from './Assignments';
import {StudyTypes} from './StudyTypes';
import {taskCourse,dueLabel,useTaskCompletion} from './TaskSummary';
import {DetailPanel} from './layout/DetailPanel';
import {Button} from './components/ui/button';

export function TaskInspector({task,open,onClose}:{task:Resource;open:boolean;onClose:()=>void}){
 const courses=useQuery({queryKey:['courses'],queryFn:()=>api<Resource[]>('/courses')});
 const settings=useQuery({queryKey:['settings'],queryFn:()=>api<Resource>('/settings')});
 const steps=useQuery({queryKey:['steps',task.id],queryFn:()=>api<Resource[]>(`/tasks/${task.id}/steps`)});
 const completion=useTaskCompletion(task);
 const estimate=steps.data?.length&&steps.data.every(s=>Number.isFinite(s.data.estimated_minutes))?steps.data.reduce((n,s)=>n+s.data.estimated_minutes,0):null;
 return <DetailPanel open={open} title={task.data.title} heading="任务详情" onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>关闭</Button><Button disabled={completion.busy||task.data.status==='archived'} onClick={()=>void completion.toggle()}>{completion.busy?'正在保存…':task.data.status==='completed'?'重新打开':'标记完成'}</Button></>}>
  <h2 className="task-detail-title">{task.data.title}</h2><small>{taskCourse(task,courses.data??[])}</small>
  <dl className="task-detail-attributes"><dt>截止</dt><dd>{dueLabel(task.data.due_at,settings.data?.data.timezone??'Asia/Shanghai')}</dd><dt>预计</dt><dd>{estimate===null?'待估时':`${estimate} 分钟`}</dd><dt>状态</dt><dd>{task.data.status==='completed'?'已完成':task.data.status==='archived'?'已归档':'未完成'}</dd></dl>
  <h3>任务要求</h3><div className="task-requirements">{task.data.requirements?.length?task.data.requirements.map((r:string,i:number)=><p key={i}>{r}</p>):<p>未填写</p>}</div>
  {!!steps.data?.length&&<section className="task-detail-steps"><h3>步骤</h3>{steps.data.map(step=><div className="task-detail-step" key={step.id}><span aria-label={step.data.status==='completed'?'已完成':'未完成'} className="step-status-box">{step.data.status==='completed'?'✓':''}</span><span>{step.data.title}</span><small>{step.data.estimated_minutes==null?'待估时':`${step.data.estimated_minutes} 分钟`}</small></div>)}</section>}
  {completion.error&&<p role="alert">{completion.error}</p>}{steps.error&&<p role="alert">{String(steps.error)}</p>}
  <details className="task-advanced"><summary>编辑与执行</summary><TaskCard task={task} expanded/><StudyTypes targetId={task.id}/></details>
 </DetailPanel>;
}
