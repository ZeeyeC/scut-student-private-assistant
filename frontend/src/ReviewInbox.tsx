import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {visibleDrafts} from './drafts';
import {DraftReview} from './DraftReview';
import {ProactiveSuggestions} from './ProactiveSuggestions';
import {DurationSuggestions} from './DurationSuggestions';
import {DetailPanel} from './layout/DetailPanel';

export function ReviewInbox({onOpenTask}:{onOpenTask:(id:string)=>void}) {
  const [open,setOpen]=useState(false),[tab,setTab]=useState('drafts');
  const drafts=useQuery({queryKey:['drafts'],queryFn:()=>api<Resource[]>('/drafts')});
  const proactive=useQuery({queryKey:['proactive','suggestions'],queryFn:()=>api<{suggestions:Resource[]}>('/proactive/suggestions')});
  const duration=useQuery({queryKey:['duration-suggestions'],queryFn:()=>api<{suggestions:Resource[]}>('/duration-suggestions')});
  const pending=visibleDrafts(drafts.data).filter(d=>d.data.status==='pending');
  const count=pending.length+(proactive.data?.suggestions.filter(s=>s.data.state==='pending').length??0)+(duration.data?.suggestions.filter(s=>s.data.state==='pending').length??0);
  useEffect(()=>{const show=()=>{setTab('drafts');setOpen(true);};window.addEventListener('campus-open-review',show);return()=>window.removeEventListener('campus-open-review',show);},[]);
  return <>
    <div className="workspace-tools"><button className="review-inbox-button" type="button" onClick={()=>setOpen(true)}>待确认{count>0?` · ${count}`:''}</button></div>
    <DetailPanel open={open} title="待确认" onClose={()=>setOpen(false)}>
      <div className="workspace-tabs">{[['drafts','草稿'],['suggestions','建议'],['duration','时长']].map(([id,label])=><button type="button" key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>
      <div hidden={tab!=='drafts'}>{drafts.error&&<p role="alert">{String(drafts.error)}</p>}{!drafts.isPending&&!pending.length&&<p>暂无待确认草稿。</p>}{pending.map(d=><DraftReview key={d.id+':'+d.revision} draft={d}/>)}</div>
      <div hidden={tab!=='suggestions'}><ProactiveSuggestions onOpenTask={id=>{setOpen(false);onOpenTask(id);}}/></div>
      <div hidden={tab!=='duration'}><DurationSuggestions/></div>
    </DetailPanel>
  </>;
}
