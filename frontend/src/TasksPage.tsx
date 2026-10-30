import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {AssignmentsPage,TaskCard} from './Assignments';
import {StudyTypes} from './StudyTypes';
import {Goals} from './Goals';
import {WeeklyReview} from './WeeklyReview';
import {NegotiationPanel} from './NegotiationPanel';
import {DetailPanel} from './layout/DetailPanel';
import type {TaskTab} from './layout/navigation';
import {Button} from './components/ui/button';

export function TasksPage({tab='todo',onTab,taskId,focusRequest}:{tab?:TaskTab;onTab:(tab:TaskTab)=>void;taskId?:string;focusRequest:number}) {
  const tasks=useQuery({queryKey:['tasks'],queryFn:()=>api<Resource[]>('/tasks')});
  const [search,setSearch]=useState(''),[status,setStatus]=useState('open');
  const [create,setCreate]=useState(false),[selected,setSelected]=useState<string>();
  const [detailOpen,setDetailOpen]=useState(false);
  useEffect(()=>{if(taskId){setSelected(taskId);setDetailOpen(true);}},[taskId,focusRequest]);
  const selectedTask=tasks.data?.find(task=>task.id===selected);
  const task=useQuery({queryKey:['task',selected],queryFn:()=>api<Resource>(`/tasks/${selected}`),enabled:!!selected&&!selectedTask});
  const record=selectedTask??task.data;
  const visible=(tasks.data??[]).filter(task=>(status==='all'||task.data.status===status)&&task.data.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <>
    <div className="page-head"><h1>任务</h1>{tab==='todo'&&<Button onClick={()=>setCreate(true)}>新建任务</Button>}</div>
    <div className="workspace-tabs" role="group" aria-label="任务分类">{(['todo','goals','review'] as const).map((value,index)=><button type="button" key={value} aria-pressed={tab===value} onClick={()=>onTab(value)}>{['待办','目标','复盘'][index]}</button>)}</div>
    {tab==='goals'?<Goals/>:tab==='review'?<><WeeklyReview/><details><summary>调整下一周安排</summary><NegotiationPanel/></details></>:<>
      <div className="task-filters"><label>搜索任务<input type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="任务名称"/></label><label>任务状态<select value={status} onChange={e=>setStatus(e.target.value)}><option value="open">待办</option><option value="completed">已完成</option><option value="all">全部</option></select></label></div>
      {tasks.isPending&&<p role="status">正在读取任务…</p>}{tasks.error&&<p role="alert">{String(tasks.error)}</p>}
      <section aria-label="任务列表" className="task-list">{visible.map(task=><button type="button" className="task-list-row" key={task.id} onClick={()=>{setSelected(task.id);setDetailOpen(true);}}><span className="task-status-mark" aria-hidden="true">{task.data.status==='completed'?'✓':'○'}</span><span><strong>{task.data.title}</strong><small>{task.data.due_at?`截止 ${new Date(task.data.due_at).toLocaleString('zh-CN')}`:'截止时间待确认'}</small></span><span className="task-row-status">{task.data.status==='completed'?'已完成':task.data.status==='archived'?'已归档':'待办'}</span></button>)}</section>
      {!tasks.isPending&&!visible.length&&<p>{search?'没有匹配的任务。':'暂无任务。'}</p>}
    </>}
    <DetailPanel open={create} title="新建任务" onClose={()=>setCreate(false)}><AssignmentsPage embedded showList={false}/></DetailPanel>
    <DetailPanel open={detailOpen} title={record?.data.title??'任务详情'} onClose={()=>setDetailOpen(false)}>
      {selected&&!record&&task.isPending&&<p role="status">正在读取任务…</p>}{task.error&&<p role="alert">{String(task.error)}</p>}
      {record&&<><TaskCard key={record.id} task={record} expanded/><StudyTypes targetId={record.id}/></>}
    </DetailPanel>
  </>;
}
