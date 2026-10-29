import {useState} from 'react';
import {useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {Button} from './components/ui/button';

export type ConflictReport = {
  issues: {id:string; severity:'conflict'|'pending'; message:string; first:{title:string;starts_at:string;ends_at:string}; second:{title:string;starts_at:string;ends_at:string}}[];
  conflict_count:number; pending_count:number; timezone?:string; conflict_token?:string;
  complete?:boolean; configuration_warnings?:string[];
};
export function ConflictReview({report, timezone='Asia/Shanghai'}:{report:ConflictReport;timezone?:string}) {
  const [all,setAll]=useState(false);
  const when=(s:string)=>new Date(s).toLocaleString('zh-CN',{timeZone:report.timezone??timezone,hour12:false});
  return <section aria-label="冲突检查" className="conflict-review">
    <h3>冲突检查：{report.conflict_count} 项冲突，{report.pending_count} 项待补充</h3>
    {report.configuration_warnings?.map(w=><p role="alert" key={w}>{w}。可继续核对并保存已确认的事实，补齐设置后再检查。</p>)}
    {report.issues.length===0 && report.complete!==false && <p>在已填写的课程和固定事项中未发现时间冲突。校内不同教室间的步行时间暂未检查。</p>}
    {(all?report.issues:report.issues.slice(0,10)).map(i=><div key={i.id} className="step">
      <p><strong>{i.severity==='pending'?'待补充':'冲突'} · {i.message}</strong></p>
      <p>{i.first.title}：{when(i.first.starts_at)} – {when(i.first.ends_at)}</p>
      <p>{i.second.title}：{when(i.second.starts_at)} – {when(i.second.ends_at)}</p>
    </div>)}
    {!all && report.issues.length>10 && <Button type="button" variant="outline" onClick={()=>setAll(true)}>查看其余 {report.issues.length-10} 项</Button>}
  </section>;
}

type Transfer = {from_campus:string;to_campus:string;minutes:number};
export function CampusTransfers() {
  const q=useQueryClient();
  const settings=useQuery({queryKey:['settings'],queryFn:()=>api<Resource>('/settings')});
  const [open,setOpen]=useState(false);
  if(!settings.data)return null;
  return <section className="card" aria-label="校区转移设置">
    <Button type="button" variant="outline" onClick={()=>setOpen(!open)}>{open?'收起校区转移时间':'设置校区转移时间'}</Button>
    {open && <TransferForm key={settings.data.revision} settings={settings.data} onSave={()=>q.invalidateQueries()} />}
  </section>;
}
function TransferForm({settings,onSave}:{settings:Resource;onSave:()=>Promise<unknown>}) {
  const [rules,setRules]=useState<Transfer[]>(settings.data.campus_transfers??[]);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false);
  return <form aria-label="编辑校区转移时间" onSubmit={async e=>{
    e.preventDefault();setBusy(true);setError('');
    try {await api('/settings',{method:'PUT',body:JSON.stringify({revision:settings.revision,data:{...settings.data,campus_transfers:rules}})});setSaved(true);await onSave();}
    catch(e){setError(String(e));}finally{setBusy(false);}
  }}>
    <p>按你实际出行所需时间填写，校区名需与课程一致。A → B 和 B → A 分别设置；未填写的方向会显示待补充。保存后用于冲突检查，通勤占用时段将在后续排程功能中加入。</p>
    <fieldset disabled={busy}>
      {rules.map((r,i)=><div className="grid2" key={i}>
        <label>出发校区<input required maxLength={100} value={r.from_campus} onChange={e=>setRules(rules.map((v,j)=>i===j?{...v,from_campus:e.target.value}:v))} /></label>
        <label>到达校区<input required maxLength={100} value={r.to_campus} onChange={e=>setRules(rules.map((v,j)=>i===j?{...v,to_campus:e.target.value}:v))} /></label>
        <label>所需分钟<input required type="number" min={1} max={360} step={1} value={r.minutes || ''} onChange={e=>setRules(rules.map((v,j)=>i===j?{...v,minutes:Number(e.target.value)}:v))} /></label>
        <Button type="button" variant="outline" onClick={()=>setRules(rules.filter((_,j)=>i!==j))}>删除此方向</Button>
      </div>)}
      <Button type="button" variant="outline" disabled={rules.length>=100} onClick={()=>setRules([...rules,{from_campus:'',to_campus:'',minutes:0}])}>添加一个方向</Button>{' '}
      <Button disabled={busy}>{busy?'正在保存…':'确认转移时间并保存'}</Button>
    </fieldset>
    {error&&<p role="alert">{error}</p>}{saved&&<p role="status">转移设置已保存</p>}
  </form>;
}
