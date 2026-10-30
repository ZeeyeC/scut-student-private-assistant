import {useEffect,useState,lazy,Suspense} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {FileImage,Text,ChevronDown} from 'lucide-react';
import {api} from './api';
import type {Course,Resource} from './types';
import {DetailPanel} from './layout/DetailPanel';
import {SchoolImportContent,SchoolExtensionGuide,activeImportStatuses,importStatusLabels} from './SchoolImportPanel';
import {TimetableRecognitionInput} from './TimetableRecognition';
import {CourseForm} from './CourseForm';
import {DraftReview} from './DraftReview';
import {visibleDrafts} from './drafts';
import {Button} from './components/ui/button';
type Method='school'|'image'|'text';
const ChatPage=lazy(()=>import('./Chat').then(module=>({default:module.ChatPage})));

export function TimetableImportHost(){
 const [open,setOpen]=useState(false),[method,setMethod]=useState<Method>('school'),[request,setRequest]=useState(0);
 const sessions=useQuery({queryKey:['browser-imports'],queryFn:()=>api<Resource[]>('/browser-imports'),refetchInterval:2000});
 const show=(value:Method='school')=>{setMethod(value);setRequest(v=>v+1);setOpen(true);};
 useEffect(()=>{const handler=(event:Event)=>show((event as CustomEvent)?.detail?.method==='image'?'image':'school');window.addEventListener('campus-start-import',handler);return()=>window.removeEventListener('campus-start-import',handler);},[]);
 const latest=sessions.data?.at(-1);
 return <>{!open&&latest&&activeImportStatuses.includes(latest.data.status)&&<button type="button" className="import-progress" onClick={()=>show()}>{importStatusLabels[latest.data.status]}</button>}<TimetableImportPanel open={open} onClose={()=>setOpen(false)} initialMethod={method} openRequest={request} onRequireOpen={()=>show()}/></>;
}

export function TimetableImportPanel({open,onClose,initialMethod='school',openRequest=0,onRequireOpen}:{open:boolean;onClose:()=>void;initialMethod?:Method;openRequest?:number;onRequireOpen?:()=>void}){
 const q=useQueryClient();
 const [imageOpen,setImageOpen]=useState(false),[textOpen,setTextOpen]=useState(false),[textMounted,setTextMounted]=useState(false),[manual,setManual]=useState(false);
 const drafts=useQuery({queryKey:['drafts'],queryFn:()=>api<Resource[]>('/drafts')});
 useEffect(()=>{if(open){setImageOpen(initialMethod==='image');setTextOpen(initialMethod==='text');if(initialMethod==='text')setTextMounted(true);}},[open,initialMethod,openRequest]);
 async function saveCourse(course:Course){await api('/drafts/timetable',{method:'POST',body:JSON.stringify({courses:[course],semester_label:'手工录入',completeness:'partial'})});setManual(false);await q.invalidateQueries({queryKey:['drafts']});}
 const reviews=visibleDrafts(drafts.data).filter(d=>['timetable','timetable_recognition','timetable_text'].includes(d.data.draft_kind));
 return <DetailPanel open={open} title="导入课表" onClose={onClose}>
  <SchoolImportContent onRequireOpen={()=>onRequireOpen?.()}/>
  <h3 className="import-other-heading">其他方式</h3>
  <button type="button" className="timetable-import-method" aria-label="图片 / PDF" aria-expanded={imageOpen} onClick={()=>setImageOpen(v=>!v)}><span><FileImage size={16}/><span><strong>图片 / PDF</strong><small>选择课表截图或文件</small></span></span><ChevronDown size={16}/></button>
  <div className="timetable-import-expanded" hidden={!imageOpen}><TimetableRecognitionInput/></div>
  <button type="button" className="timetable-import-method" aria-label="文字导入" aria-expanded={textOpen} onClick={()=>{setTextMounted(true);setTextOpen(v=>!v);}}><span><Text size={16}/><span><strong>文字导入</strong><small>粘贴课程、时间和周次</small></span></span><ChevronDown size={16}/></button>
  <div className="timetable-import-expanded" hidden={!textOpen}>{textMounted&&<Suspense fallback={<p role="status">正在打开文字输入…</p>}><ChatPage embedded courseEntry reviewOutside/></Suspense>}<Button variant="outline" onClick={()=>setManual(v=>!v)}>手工添加课程</Button><div hidden={!manual}><CourseForm onSave={saveCourse}/></div></div>
  <SchoolExtensionGuide visible={open}/>
  {reviews.map(d=><div key={d.id} id={`timetable-draft-${d.id}`} tabIndex={-1}><DraftReview draft={d}/></div>)}
 </DetailPanel>;
}
