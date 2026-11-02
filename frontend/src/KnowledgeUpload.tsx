import {useRef,useState} from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {Upload,X} from 'lucide-react';
import {useQueryClient} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {validateDocFiles} from './chat-documents';
import {courseLabel} from './knowledge-library';
type Entry={file:File;key:string;done:boolean;error?:string};
export function KnowledgeUpload({open,onClose,courses,initialCourse}:{open:boolean;onClose:()=>void;courses:Resource[];initialCourse:string}){
 const q=useQueryClient(),[course,setCourse]=useState(initialCourse),[entries,setEntries]=useState<Entry[]>([]),[busy,setBusy]=useState(false),[attempted,setAttempted]=useState(false),[error,setError]=useState('');const input=useRef<HTMLInputElement>(null);
 function add(files:File[]){if(busy)return;try{validateDocFiles(files,entries.length);setEntries(old=>[...old,...files.map(file=>({file,key:crypto.randomUUID(),done:false}))]);setError('');}catch(e){setError(String(e));}}
 async function send(){if(busy||!entries.some(e=>!e.done))return;setBusy(true);setAttempted(true);setError('');let failed=false;const updated=[...entries];try{for(let i=0;i<updated.length;i++){const e=updated[i];if(e.done)continue;try{const fd=new FormData();fd.append('file',e.file);if(course)fd.append('course_id',course);await api('/knowledge/documents',{method:'POST',headers:{'Idempotency-Key':e.key},body:fd});updated[i]={...e,done:true,error:undefined};}catch(err){failed=true;updated[i]={...e,error:String(err)};}setEntries([...updated]);}await q.invalidateQueries({queryKey:['knowledge']});await q.invalidateQueries({queryKey:['knowledge-sources']});if(!failed)onClose();else setError('部分文件未能添加，可移除失败项或重试。');}finally{setBusy(false);}}
 return <Dialog.Root open={open} onOpenChange={v=>{if(!v&&!busy)onClose();}}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="knowledge-upload" onEscapeKeyDown={e=>{if(busy)e.preventDefault();}} onPointerDownOutside={e=>{if(busy)e.preventDefault();}}>
 <header className="kb-detailhead"><Dialog.Title>上传资料</Dialog.Title><button className="kb-icon" type="button" aria-label="关闭上传资料" onClick={onClose} disabled={busy}><X size={18}/></button></header><Dialog.Description className="sr-only">选择课程并添加资料；点击添加后才在本机解析入库。</Dialog.Description>
 <label className="kb-field">所属课程<select aria-label="所属课程" value={course} onChange={e=>setCourse(e.target.value)} disabled={busy||attempted}><option value="">未分类</option>{courses.map(c=><option value={c.id} key={c.id}>{courseLabel(c,courses)}</option>)}</select></label>
 <div className="kb-drop" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();add(Array.from(e.dataTransfer.files));}}><Upload size={22}/><button className="kb-button" type="button" onClick={()=>input.current?.click()} disabled={busy}>选择文件</button><span>或拖入文件</span><small>PDF、Word、PPT、Excel、TXT、Markdown</small><input ref={input} type="file" multiple hidden accept=".pdf,.docx,.pptx,.xlsx,.txt,.md" aria-label="选择资料文件" onChange={e=>{if(e.target.files?.length)add(Array.from(e.target.files));e.target.value='';}}/></div>
 <ul className="kb-upload-files">{entries.map(e=><li key={e.key}><div><span>{e.file.name}</span><small>{e.done?'已添加':e.error?'添加失败':'待添加'}</small>{e.error&&<p role="alert">{e.error}</p>}</div>{!e.done&&<button className="kb-icon" type="button" aria-label={`移除${e.file.name}`} disabled={busy} onClick={()=>setEntries(old=>old.filter(v=>v.key!==e.key))}><X size={16}/></button>}</li>)}</ul>
 {error&&<p role="alert">{error}</p>}<footer className="kb-dialogfooter"><button className="kb-button" type="button" onClick={onClose} disabled={busy}>取消</button><button className="kb-button kb-primary" type="button" onClick={()=>void send()} disabled={busy||!entries.some(e=>!e.done)}>{busy?'正在添加…':entries.some(e=>e.error)?'重试失败文件':'添加到资料库'}</button></footer>
 </Dialog.Content></Dialog.Portal></Dialog.Root>;
}
