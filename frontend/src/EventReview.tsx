import { useState } from 'react';
import { DraftActions } from './Assignments';
import type { Resource } from './types';

const localInput = (value: string) => {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
export function EventReview({draft}: {draft: Resource}) {
  const [payload, setPayload] = useState(draft.data.payload);
  const [error, setError] = useState('');
  return <section className="card">
    <p className="eyebrow">日程草稿 · 尚未保存</p>
    <h2>核对日程事项</h2>
    <p>确认后出现在待办与日程和今日事项中，并避让七天学习计划。</p>
    <label>事项标题<input value={payload.title} onChange={e=>setPayload({...payload,title:e.target.value})} /></label>
    <div className="grid2">
      <label>开始时间（本机时区）<input type="datetime-local" value={localInput(payload.starts_at)} onChange={e=>{if(e.target.value)setPayload({...payload,starts_at:new Date(e.target.value).toISOString()});}} /></label>
      <label>结束时间（本机时区）<input type="datetime-local" value={localInput(payload.ends_at)} onChange={e=>{if(e.target.value)setPayload({...payload,ends_at:new Date(e.target.value).toISOString()});}} /></label>
    </div>
    {error && <p role="alert">{error}</p>}
    <DraftActions draft={draft} payload={payload} onError={setError}/>
  </section>;
}
