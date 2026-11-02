import {useEffect,useRef,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import {Button} from './components/ui/button';
import type {Resource} from './types';

// Chat picker only. Upload, classification, deletion and full browsing live on
// the standalone page; both read the same owned sources.
export function KnowledgeManager({onSelect,selectedIds=[],disabled=false}:{onSelect?:(source:Resource)=>void;selectedIds?:string[];disabled?:boolean}){
 const [filter,setFilter]=useState(''),[query,setQuery]=useState(''),[hits,setHits]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const sources=useQuery({queryKey:['knowledge-sources'],queryFn:({signal})=>api<{items:Resource[]}>('/knowledge/library?limit=100',{signal}).then(r=>r.items)});
 const courses=useQuery({queryKey:['courses'],queryFn:()=>api<Resource[]>('/courses')});
 const generation=useRef(0);
 useEffect(()=>{generation.current++;setHits(null);},[filter,query,sources.data]);
 useEffect(()=>()=>{generation.current++;},[]);
 const visible=(sources.data??[]).filter(s=>!filter||s.data.course_id===filter);
 return <section aria-label="已有资料选择器"><p className="muted">选择已有资料用于本次对话。</p>
 <label>筛选课程<select disabled={disabled} value={filter} onChange={e=>setFilter(e.target.value)}><option value="">全部课程</option>{courses.data?.map(c=><option key={c.id} value={c.id}>{c.data.name}</option>)}</select></label>
 <form onSubmit={async e=>{e.preventDefault();if(!query.trim()||busy)return;setBusy(true);setError('');const epoch=++generation.current;try{const result=await api('/knowledge/search',{method:'POST',body:JSON.stringify({query,...(filter?{course_id:filter}:{})})});if(epoch===generation.current)setHits(result);}catch(err){if(epoch===generation.current)setError(String(err));}finally{setBusy(false);}}}><label>检索资料内容<input value={query} placeholder="输入关键词或问题…" onChange={e=>setQuery(e.target.value)} disabled={disabled||busy}/></label><Button variant="outline" disabled={disabled||busy||!query.trim()}>检索</Button></form>
 {error&&<p role="alert">{error}</p>}{sources.error&&<p role="alert">{String(sources.error)}</p>}{sources.isPending&&<p role="status">正在加载资料…</p>}
 {hits&&<div>{hits.items.map((h:any,i:number)=><p key={i}><strong>{h.title}</strong> · {h.location}：{h.text}</p>)}</div>}
 {!sources.isPending&&!visible.length&&<p className="muted">暂无匹配的课程资料。</p>}{visible.map(s=><div key={s.id} style={{borderTop:'1px solid var(--workspace-line)',padding:'12px 0',display:'flex',justifyContent:'space-between',alignItems:'center',gap:12}}><div style={{minWidth:0,overflowWrap:'anywhere'}}><strong>{s.data.filename||s.data.title}</strong><small style={{display:'block'}}>{s.data.course_missing?'原课程已移除':s.data.course_name||'未分类'}</small></div>{onSelect&&<Button type="button" disabled={disabled} variant={selectedIds.includes(s.id)?'default':'outline'} onClick={()=>onSelect(s)}>{selectedIds.includes(s.id)?'已选用':'选用'}</Button>}</div>)}
 </section>;
}
export default KnowledgeManager;
