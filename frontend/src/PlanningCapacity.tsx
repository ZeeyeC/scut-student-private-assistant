import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import { Button } from './components/ui/button';
import type { components } from './generated-api';

type Report = components['schemas']['CapacityReport'];

export function PlanningCapacity() {
  const [scope, setScope] = useState<'today' | 'range'>('today');
  const report = useQuery({
    queryKey: ['planning-capacity', scope],
    queryFn: () => api<Report>('/planning-capacity?scope=' + scope),
  });
  const p = report.data;
  const clock = (value: string) => new Date(value).toLocaleTimeString('zh-CN', {
    timeZone: p?.timezone, hour: '2-digit', minute: '2-digit', hour12: false,
  });
  return <section className="card" aria-label="时间容量检查">
    <h2>时间够用吗？</h2>
    <p>扣除课程、固定事项、缓冲、禁排及保留安排，按学习窗口和每日上限检查。仅预览，生成并确认计划后才改变日程。</p>
    <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
      <Button variant={scope === 'today' ? 'default' : 'outline'} aria-pressed={scope === 'today'} onClick={() => setScope('today')}>今天剩余时间</Button>
      <Button variant={scope === 'range' ? 'default' : 'outline'} aria-pressed={scope === 'range'} onClick={() => setScope('range')}>未来7天容量</Button>
      <Button variant="outline" disabled={report.isFetching} onClick={() => report.refetch()}>刷新容量</Button>
    </div>
    {report.isFetching && <p role="status">正在核对时间与待办…</p>}
    {report.error && <p role="alert">容量检查失败：{String(report.error)}，请点击刷新容量重试。</p>}
    {p && !report.error && <div aria-busy={report.isFetching}>
      <p><strong>容量上限 {p.capacity_upper_bound_minutes} 分钟</strong> · 待分配 {p.required_minutes} 分钟 · 本范围可排 {p.proposed_minutes} 分钟 · 仍未排 {p.unallocated_minutes} 分钟</p>
      <p>另有 {p.reserved_work_minutes} 分钟已由保留安排预留（可能在本范围之外），未重复计入待分配。{p.unknown_estimate_count > 0 ? `还有 ${p.unknown_estimate_count} 项待办缺少步骤耗时，未计入分钟合计。` : '以上基于已有步骤耗时，不代表实际学习投入。'}</p>
      <p>容量上限只表示时间与每日预算；截止时间、依赖及零碎空档可能让实际可排更少。</p>
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12}}>
        {p.days.map(day => <article className="step" key={day.date} aria-label={day.date + ' 容量'}>
          <h3>{day.date}</h3>
          <p>空档 {day.free_minutes} 分钟 · 剩余学习预算 {day.budget_remaining_minutes} 分钟</p>
          <p>容量上限 {day.capacity_upper_bound_minutes} 分钟 · 可排 {day.proposed_minutes} 分钟</p>
          <details><summary>查看可用空档</summary>
            {day.free_windows.length === 0 ? <p>没有可用空档。</p> : day.free_windows.map((w, i) => <p key={i}>{clock(w.starts_at)}–{clock(w.ends_at)} · {w.minutes} 分钟</p>)}
          </details>
        </article>)}
      </div>
      {p.unscheduled.length > 0 && <div><h3>未排下的工作</h3>{p.unscheduled.map((u, i) => <p key={u.step_id ?? u.task_id ?? i}><strong>{u.title}</strong>：{u.remaining_minutes == null ? '耗时未知' : `${u.remaining_minutes} 分钟`} · {u.reason}</p>)}</div>}
      {p.warnings.map((warning, i) => <p role="alert" key={i}>{warning}</p>)}
      <p>重新生成的预览差异：新增 {p.changes.added} 项、保留 {p.changes.retained} 项、替换或移除 {p.changes.removed} 项。尚未保存。</p>
      <small>{p.timezone} · 核对时间 {clock(p.calculated_at)} · 资料版本 {p.source_revision}</small>
    </div>}
  </section>;
}
