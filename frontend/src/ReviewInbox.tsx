import {useEffect,useState,type ReactNode} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {visibleDrafts} from './drafts';
import {DraftReview} from './DraftReview';
import {ProactiveSuggestions} from './ProactiveSuggestions';
import {DurationSuggestions} from './DurationSuggestions';
import {DetailPanel} from './layout/DetailPanel';
import {ReviewContext} from './layout/review-context';

export function ReviewInbox({onOpenTask,children}:{onOpenTask:(id:string)=>void;children?:ReactNode}) {
  const [open,setOpen]=useState(false),[tab,setTab]=useState('drafts');
  const drafts=useQuery({queryKey:['drafts'],queryFn:()=>api<Resource[]>('/drafts')});
  const proactive=useQuery({queryKey:['proactive','suggestions'],queryFn:()=>api<{suggestions:Resource[]}>('/proactive/suggestions')});
  const duration=useQuery({queryKey:['duration-suggestions'],queryFn:()=>api<{suggestions:Resource[]}>('/duration-suggestions')});
  const pending=visibleDrafts(drafts.data).filter(d=>d.data.status==='pending');
  const count=pending.length+(proactive.data?.suggestions.filter(s=>s.data.state==='pending').length??0)+(duration.data?.suggestions.filter(s=>s.data.state==='pending').length??0);
  useEffect(()=>{
    if(open){void drafts.refetch();void proactive.refetch();void duration.refetch();}
  },[open,tab]);
  useEffect(()=>{const show=()=>{setTab('drafts');setOpen(true);};window.addEventListener('campus-open-review',show);return()=>window.removeEventListener('campus-open-review',show);},[]);
  return <ReviewContext.Provider value={{count,open:()=>setOpen(true)}}>
    {children}
    <DetailPanel open={open} title="待确认" onClose={()=>setOpen(false)}>
      <div className="workspace-tabs">{[['drafts','草稿'],['suggestions','建议'],['duration','时长']].map(([id,label])=><button type="button" key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>
      <div hidden={tab!=='drafts'}>{drafts.error&&<p role="alert">{String(drafts.error)}</p>}{!drafts.isPending&&!pending.length&&<p>暂无待确认草稿。</p>}{pending.map(d=><DraftReview key={d.id+':'+d.revision} draft={d}/>)}</div>
      <div hidden={tab!=='suggestions'}><ProactiveSuggestions onOpenTask={id=>{setOpen(false);onOpenTask(id);}}/></div>
      <div hidden={tab!=='duration'}><DurationSuggestions/></div>
    </DetailPanel>
  </ReviewContext.Provider>;
}
