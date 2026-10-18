import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { ScheduleEvent } from './schedule';
import { Button } from './components/ui/button';

type Config = { revision: number; enabled: boolean; target_kind: 'none' | 'website' | 'file'; target: string };
export function ScheduleShortcut({ event }: { event: ScheduleEvent }) {
  const config = useQuery({ queryKey: ['schedule-shortcut', event.id, event.starts_at], queryFn: () => api<Config>(`/schedule-shortcut?${new URLSearchParams({event_id:event.id, starts_at:event.starts_at})}`) });
  const [value, setValue] = useState<Config | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const bridge = (window as unknown as { webkit?: { messageHandlers?: { petState?: { postMessage: (s:string)=>void } } } }).webkit?.messageHandlers?.petState;
  useEffect(() => { if(config.data) setValue(config.data); }, [config.data]);
  useEffect(() => {
    const chosen = (e: Event) => { const path = (e as CustomEvent).detail; if(typeof path === 'string') setValue(v => v ? {...v, target_kind:'file', target:path} : v); };
    window.addEventListener('campus-reminder-file', chosen);
    return () => window.removeEventListener('campus-reminder-file', chosen);
  }, []);
  return <section aria-label="提醒与快捷打开">
    <h3>提醒与快捷打开</h3>
    <p>桌宠运行时，在开始前 5 分钟提醒一次。奶娃变紫后点击肚皮打开指定内容；未指定则打开待办与日程。此设置仅用于这一条日程。</p>
    {config.error && <p role="alert">{String(config.error)}</p>}
    {!value ? <p>正在读取…</p> : <form onSubmit={async e => {
      e.preventDefault(); setBusy(true); setMessage('');
      try { const saved = await api<Config>('/schedule-shortcut', {method:'PUT', body:JSON.stringify({...value, event_id:event.id, starts_at:event.starts_at})}); setValue(saved); setMessage('已保存'); }
      catch(error) { setMessage(String(error)); }
      finally { setBusy(false); }
    }}>
      <label><input type="checkbox" checked={value.enabled} onChange={e=>setValue({...value, enabled:e.target.checked})}/>开始前 5 分钟提醒</label>
      <label>点击奶娃时打开<select value={value.target_kind} onChange={e=>setValue({...value, target_kind:e.target.value as Config['target_kind'], target:''})}>
        <option value="none">待办与日程</option><option value="website">网站</option><option value="file">本机文件</option>
      </select></label>
      {value.target_kind !== 'none' && <label>{value.target_kind === 'website' ? '完整网站地址' : '文件完整路径'}<input required type={value.target_kind === 'website' ? 'url' : 'text'} placeholder={value.target_kind === 'website' ? 'https://…' : '/Users/…/作业.pdf'} value={value.target} onChange={e=>setValue({...value, target:e.target.value})}/></label>}
      {value.target_kind === 'file' && bridge && <Button type="button" variant="outline" onClick={()=>bridge.postMessage('choose-reminder-file')}>选择本机文件…</Button>}
      {value.target_kind === 'file' && !bridge && <p>可粘贴文件完整路径，或在桌宠 App 中选择文件。</p>}
      <Button disabled={busy}>{busy ? '保存中…' : '保存提醒设置'}</Button>
      {message && <p role="status">{message}</p>}
    </form>}
  </section>;
}
