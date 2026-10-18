import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { Resource } from './types';
import { TaskCard } from './Assignments';
import { Button } from './components/ui/button';
import { navigate } from './drafts';

export function TodoList() {
  const tasks = useQuery({queryKey:['tasks'],queryFn:()=>api<Resource[]>('/tasks')});
  const drafts = useQuery({queryKey:['drafts'],queryFn:()=>api<Resource[]>('/drafts')});
  const open = tasks.data?.filter(t=>t.data.status==='open') ?? [];
  const pending = drafts.data?.filter(d=>d.data.draft_kind==='assignment').length ?? 0;
  return <section aria-label="我的待办" className="card">
    <h2>我的待办</h2>
    <p>已保存的待办列在这里；有固定起止时间的活动请到待办与日程添加固定事项。</p>
    {tasks.isPending && <p role="status">正在读取待办…</p>}
    {tasks.error && <p role="alert">{String(tasks.error)}</p>}
    {!tasks.isPending && !open.length && <p>还没有已保存的待办。</p>}
    {pending > 0 && <p>还有 {pending} 份待办草稿尚未确认保存。</p>}
    {open.map(t=><TaskCard key={t.id} task={t}/>)}
    <Button variant="outline" onClick={()=>navigate('作业')}>查看全部待办与草稿</Button>
  </section>;
}
