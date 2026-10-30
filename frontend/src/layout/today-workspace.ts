import type {Resource} from '../types';

export function selectTodayTasks(tasks:Resource[],blocks:Resource[],now:Date,timezone:string) {
  const day=now.toLocaleDateString('en-CA',{timeZone:timezone});
  const open=tasks.filter(task=>task.data.status==='open');
  const candidate=blocks.filter(block=>{
    const start=new Date(block.data.starts_at),end=new Date(block.data.ends_at);
    return block.data.status!=='completed'&&end>now&&start.toLocaleDateString('en-CA',{timeZone:timezone})<=day&&end.toLocaleDateString('en-CA',{timeZone:timezone})>=day&&open.some(task=>task.id===block.data.task_id);
  }).sort((a,b)=>Date.parse(a.data.starts_at)-Date.parse(b.data.starts_at))[0];
  const next=open.find(task=>task.id===candidate?.data.task_id)??open[0];
  return {next,block:candidate,others:open.filter(task=>task.id!==next?.id).slice(0,2)};
}
