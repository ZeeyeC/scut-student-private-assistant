import type { CourseIntervalsData } from './schedule';

export function CourseIntervals({event, timezone}: {event: CourseIntervalsData; timezone: string}) {
  if (!event.teaching_intervals?.length) return null;
  const clock = (value: string) => new Date(value).toLocaleTimeString('zh-CN', {timeZone: timezone, hour: '2-digit', minute: '2-digit'});
  return <div aria-label="授课与课间休息">
    <p>实际授课：{event.teaching_intervals.map((part) => `${part.periods?.length ? `第${part.periods.join('、')}节 ` : ''}${clock(part.starts_at)}–${clock(part.ends_at)}`).join('；')}</p>
    {!!event.break_intervals?.length && <p>课间休息（不安排任务）：{event.break_intervals.map((part) => `${clock(part.starts_at)}–${clock(part.ends_at)}`).join('；')}</p>}
  </div>;
}
