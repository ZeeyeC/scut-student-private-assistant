import {expect,it} from 'vitest';
import {selectTodayTasks} from './today-workspace';
import type {Resource} from '../types';
const task=(id:string,status='open')=>({id,kind:'task',revision:1,data:{title:id,status}} as Resource);
const block=(id:string,taskId:string,start:string,end:string,status='suggested')=>({id,kind:'plan_block',revision:1,data:{task_id:taskId,starts_at:start,ends_at:end,status}} as Resource);
it('selects the current or next open task once and limits other tasks to two',()=>{
  const tasks=[task('old'),task('next'),task('other'),task('four'),task('done','completed')];
  const blocks=[block('old','old','2026-10-30T08:00:00+08:00','2026-10-30T09:00:00+08:00'),block('next','next','2026-10-30T10:00:00+08:00','2026-10-30T11:00:00+08:00'),block('done','done','2026-10-30T10:00:00+08:00','2026-10-30T11:00:00+08:00')];
  const value=selectTodayTasks(tasks,blocks,new Date('2026-10-30T10:15:00+08:00'),'Asia/Shanghai');
  expect(value.next?.id).toBe('next');
  expect(value.others.map(item=>item.id)).toEqual(['old','other']);
  expect(value.block?.id).toBe('next');
});
it('keeps overnight unfinished blocks in the configured local day',()=>{
  const value=selectTodayTasks([task('night')],[block('night','night','2026-10-29T23:30:00+08:00','2026-10-30T00:30:00+08:00')],new Date('2026-10-30T00:10:00+08:00'),'Asia/Shanghai');
  expect(value.next?.id).toBe('night');
  expect(value.block?.id).toBe('night');
});
it('does not invent a task or active execution when everything is complete',()=>{
  expect(selectTodayTasks([task('done','completed')],[],new Date(),'Asia/Shanghai')).toEqual({next:undefined,block:undefined,others:[]});
});
