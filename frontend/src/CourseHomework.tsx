import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import { Button } from './components/ui/button';
import type { Resource } from './types';
import type { ScheduleEvent } from './schedule';
import { DraftReview } from './DraftReview';
import { TaskInspector } from './TaskInspector';

export function CourseHomework({ event, timezone, onResume, onPlan }: {
  event: ScheduleEvent; timezone: string; onResume: (date: string) => void; onPlan: () => void;
}) {
  const q = useQueryClient();
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: () => api<Resource[]>('/tasks') });
  const drafts = useQuery({ queryKey: ['drafts'], queryFn: () => api<Resource[]>('/drafts') });
  const [editing, setEditing] = useState(false);
  const [draftId, setDraftId] = useState('');
  const [selected, setSelected] = useState<Resource>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const receipt = useRef({ body: '', key: '' });
  const date = new Date(event.starts_at).toLocaleDateString('en-CA', { timeZone: timezone });
  const linked = (tasks.data ?? []).filter(task => {
    const ref = task.data.course_occurrence;
    return (ref?.course_id === event.course_id && ref.original_date === event.original_date)
      || task.data.course_occurrences?.some((occurrence: { id: string }) => occurrence.id === event.id);
  });
  const draft = drafts.data?.find(d => d.id === draftId);
  return <section className="course-homework" aria-label="这次课的作业">
    <h3>这次课的作业</h3>
    {linked.map(task => <button type="button" className="thread-history-row" key={task.id} onClick={() => setSelected(task)}>{task.data.title} · {task.data.status === 'completed' ? '已完成' : '未完成'}</button>)}
    {!tasks.isPending && !linked.length && <p>这次课还没有关联作业。</p>}
    {tasks.error && <p role="alert">{String(tasks.error)}</p>}
    <div className="guide-actions">
      <Button variant="outline" onClick={() => { if (!editing) receipt.current = { body: '', key: '' }; setEditing(value => !value); }}>{editing ? '收起作业表单' : Date.parse(event.ends_at) < Date.now() ? '补记作业' : '添加作业'}</Button>
      <Button variant="outline" onClick={() => onResume(date)}>查看当天课后草稿</Button>
      {!!linked.length && <Button variant="outline" onClick={onPlan}>安排学习</Button>}
    </div>
    {editing && <form className="card" onSubmit={async e => {
      e.preventDefault();
      const form = new FormData(e.currentTarget);
      const content = String(form.get('content') ?? '').trim();
      const body = JSON.stringify({ items: [{
        title: `${event.title} · ${content.split('\n')[0]}`.slice(0, 200),
        requirements: [content], course_id: event.course_id,
        course_occurrence: { course_id: event.course_id, original_date: event.original_date },
        estimated_minutes: form.get('minutes') ? Number(form.get('minutes')) : null,
        due_at: form.get('due') ? new Date(String(form.get('due'))).toISOString() : null,
      }] });
      if (body !== receipt.current.body) receipt.current = { body, key: crypto.randomUUID() };
      setBusy(true); setError('');
      try {
        const result = await api<Resource>('/drafts/assignment', { method: 'POST', headers: { 'Idempotency-Key': receipt.current.key }, body });
        setDraftId(result.id); setEditing(false);
        await q.invalidateQueries({ queryKey: ['drafts'] });
      } catch (err) { setError(String(err)); }
      finally { setBusy(false); }
    }}>
      <p>来源 {event.title} · {date}</p>
      <label>作业内容<textarea name="content" required maxLength={4000} rows={3}/></label>
      <label>预计用时（分钟，可留空）<input name="minutes" type="number" min={5} max={240}/></label>
      <label>截止时间（可留空）<input name="due" type="datetime-local"/></label>
      <Button disabled={busy}>{busy ? '正在生成…' : '生成作业草稿'}</Button>
    </form>}
    {draft?.data.status === 'pending' && <DraftReview key={`${draft.id}:${draft.revision}`} draft={draft}/>}
    {draft?.data.status === 'confirmed' && <p role="status">作业已保存，可以在任务列表和这次课程详情中查看。</p>}
    {error && <p role="alert">{error}</p>}
    {selected && <TaskInspector task={tasks.data?.find(t => t.id === selected.id) ?? selected} open onClose={() => setSelected(undefined)}/>}
  </section>;
}
