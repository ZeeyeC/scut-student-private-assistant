import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {AssignmentsPage} from './Assignments';
import {TaskInspector} from './TaskInspector';
import {TaskSummaryRow,taskCourse,useTaskEstimates} from './TaskSummary';
import {PageHeader} from './layout/PageHeader';
import {Plus,Search} from 'lucide-react';
import {Goals} from './Goals';
import {WeeklyReview} from './WeeklyReview';
import {NegotiationPanel} from './NegotiationPanel';
import {DetailPanel} from './layout/DetailPanel';
import type {TaskTab} from './layout/navigation';
import {Button} from './components/ui/button';

export function TasksPage({tab='todo',onTab,taskId,focusRequest,createRequested,onCreateHandled}:{tab?:TaskTab;onTab:(tab:TaskTab)=>void;taskId?:string;focusRequest:number;createRequested?:boolean;onCreateHandled?:()=>void}) {
  const tasks=useQuery({queryKey:['tasks'],queryFn:()=>api<Resource[]>('/tasks')});
  const courses=useQuery({queryKey:['courses'],queryFn:()=>api<Resource[]>('/courses')});
  const settings=useQuery({queryKey:['settings'],queryFn:()=>api<Resource>('/settings')});
  const [search,setSearch]=useState(''),[status,setStatus]=useState('open');
  const [create,setCreate]=useState(false),[selected,setSelected]=useState<string>();
  const [detailOpen,setDetailOpen]=useState(false);
  useEffect(()=>{if(taskId){setSelected(taskId);setDetailOpen(true);}},[taskId,focusRequest]);
  useEffect(()=>{if(createRequested){setCreate(true);onCreateHandled?.();}},[createRequested,onCreateHandled]);
  const selectedTask=tasks.data?.find(task=>task.id===selected);
  const task=useQuery({queryKey:['task',selected],queryFn:()=>api<Resource>(`/tasks/${selected}`),enabled:!!selected&&!selectedTask});
  const record=selectedTask??task.data;
  const visible=(tasks.data??[]).filter(task=>(status==='all'||task.data.status===status)&&task.data.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const estimates=useTaskEstimates(visible);
  return <>
    <PageHeader title="任务">{tab==='todo'&&<Button aria-label="新建任务" onClick={()=>setCreate(true)}><Plus size={16}/>添加任务</Button>}</PageHeader>
    <div className="workspace-tabs" role="group" aria-label="任务分类">{(['todo','goals','review'] as const).map((value,index)=><button type="button" key={value} aria-pressed={tab===value} onClick={()=>onTab(value)}>{['待办','目标','复盘'][index]}</button>)}</div>
    {tab==='goals'?<Goals/>:tab==='review'?<><WeeklyReview/><details><summary>调整下一周安排</summary><NegotiationPanel/></details></>:<>
      <div className="task-filters"><label className="task-search"><Search size={16}/><input type="search" aria-label="搜索任务" value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索任务"/></label><select aria-label="任务状态" value={status} onChange={e=>setStatus(e.target.value)}><option value="open">未完成 {visible.length}</option><option value="completed">已完成</option><option value="all">全部</option></select></div>
      {tasks.isPending&&<p role="status">正在读取任务…</p>}{tasks.error&&<p role="alert">{String(tasks.error)}</p>}
      <div className="task-table-heading"><span>任务</span><span>截止</span><span>预计</span></div><section aria-label="任务列表" className="task-list task-table">{visible.map(task=><TaskSummaryRow key={task.id} task={task} course={taskCourse(task,courses.data??[])} minutes={estimates.get(task.id)??null} timezone={settings.data?.data.timezone??'Asia/Shanghai'} table onOpen={()=>{setSelected(task.id);setDetailOpen(true);}}/>)}</section>
      {!tasks.isPending&&!visible.length&&<p>{search?'没有匹配的任务。':'暂无任务。'}</p>}
    </>}
    <DetailPanel open={create} title="新建任务" onClose={()=>setCreate(false)}><AssignmentsPage embedded showList={false}/></DetailPanel>
    {!record&&<DetailPanel open={detailOpen} title="任务详情" onClose={()=>setDetailOpen(false)}>
      {selected&&!record&&task.isPending&&<p role="status">正在读取任务…</p>}{task.error&&<p role="alert">{String(task.error)}</p>}
    </DetailPanel>}
    {record&&<TaskInspector key={record.id} task={record} open={detailOpen} onClose={()=>setDetailOpen(false)}/>}
  </>;
}
