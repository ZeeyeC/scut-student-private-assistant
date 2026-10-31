import {useEffect,useRef,useState} from 'react';
import type {ClipboardEvent,DragEvent} from 'react';
import './chat-images.css';
import {Paperclip} from 'lucide-react';

export const IMAGE_TYPES=['image/png','image/jpeg','image/webp'];
export function validateImageFiles(files:File[]){
 if(files.length!==1)throw new Error('请每次添加一张作业截图。');
 if(!IMAGE_TYPES.includes(files[0].type))throw new Error('仅支持 PNG、JPEG、WebP 图片。');
 if(files[0].size>10*1024*1024)throw new Error('图片不能超过 10 MiB。');
 return files[0];
}
export type PendingImage={file:File;url:string;uploadKey:string;runKey:string;threadKey:string;assetId?:string};
export function useChatImage(){
 const [image,setImage]=useState<PendingImage|null>(null),[error,setError]=useState('');
 const [consent,setConsent]=useState(false),[reference,setReference]=useState('');
 const generation=useRef(0),current=useRef<PendingImage|null>(null);
 const clear=()=>{generation.current++;if(current.current)URL.revokeObjectURL(current.current.url);current.current=null;setImage(null);setConsent(false);setReference('');setError('');};
 useEffect(()=>()=>{generation.current++;if(current.current)URL.revokeObjectURL(current.current.url)},[]);
 const add=async(files:File[])=>{
  const epoch=++generation.current;
  let url='';
  try{
   const file=validateImageFiles(files);url=URL.createObjectURL(file);
   await new Promise<void>((resolve,reject)=>{const img=new Image();img.onload=()=>img.naturalWidth*img.naturalHeight<=20_000_000?resolve():reject(new Error('图片不能超过 2000 万像素。'));img.onerror=()=>reject(new Error('图片无法读取，请重新选择。'));img.src=url});
   if(epoch!==generation.current){URL.revokeObjectURL(url);return;}
   if(current.current)URL.revokeObjectURL(current.current.url);
   const next={file,url,uploadKey:crypto.randomUUID(),runKey:crypto.randomUUID(),threadKey:crypto.randomUUID()};
   current.current=next;setImage(next);setConsent(false);setReference('');setError('');
  }catch(e){if(url)URL.revokeObjectURL(url);if(epoch===generation.current)setError(String(e instanceof Error?e.message:e));}
 };
 return {image,error,setError,consent,setConsent,reference,setReference,clear,add,freeze:()=>{generation.current++}};
}
export function ImageDropArea({children,disabled,onFiles}:{children:React.ReactNode;disabled:boolean;onFiles:(files:File[])=>void}){
 const [dragging,setDragging]=useState(false);
 useEffect(()=>{
  const prevent=(e:globalThis.DragEvent)=>{if(e.dataTransfer?.types.includes('Files'))e.preventDefault()};
  window.addEventListener('dragover',prevent);window.addEventListener('drop',prevent);
  return()=>{window.removeEventListener('dragover',prevent);window.removeEventListener('drop',prevent)};
 },[]);
 useEffect(()=>{if(disabled)setDragging(false)},[disabled]);
 const drag=(e:DragEvent)=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();e.dataTransfer.dropEffect=disabled?'none':'copy';setDragging(!disabled)}};
 const paste=(e:ClipboardEvent)=>{const files=Array.from(e.clipboardData.files);if(files.length){e.preventDefault();e.stopPropagation();if(!disabled)onFiles(files)}};
 return <div className="chat-image-drop" data-testid="chat-image-drop" onDragEnter={drag} onDragOver={drag} onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null))setDragging(false)}} onDrop={e=>{setDragging(false);if(e.dataTransfer.types.includes('Files')){e.preventDefault();e.stopPropagation();if(!disabled)onFiles(Array.from(e.dataTransfer.files))}}} onPasteCapture={paste}>
  {children}{dragging&&<div className="chat-drop-hint" role="status">松开添加作业截图</div>}
 </div>;
}
export function ChatImageControls({state,disabled}:{state:ReturnType<typeof useChatImage>;disabled:boolean}){
 const [menu,setMenu]=useState(false);const file=useRef<HTMLInputElement>(null),container=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(disabled)setMenu(false)},[disabled]);
 useEffect(()=>{if(!menu)return;const click=(e:MouseEvent)=>{if(!container.current?.contains(e.target as Node))setMenu(false)};const key=(e:KeyboardEvent)=>{if(e.key==='Escape')setMenu(false)};document.addEventListener('pointerdown',click);document.addEventListener('keydown',key);return()=>{document.removeEventListener('pointerdown',click);document.removeEventListener('keydown',key)}},[menu]);
 return <>
  {state.image&&<div className="chat-image-preview"><img src={state.image.url} alt="待发送的作业截图"/><span>{state.image.file.name}</span><button type="button" disabled={disabled} onClick={state.clear} aria-label="移除作业截图">移除</button></div>}
  {state.image&&<div className="chat-image-options"><label><input type="checkbox" checked={state.consent} disabled={disabled} onChange={e=>state.setConsent(e.target.checked)}/>同意将图片及课程候选发送给配置的模型供应商</label><label>截图消息日期（可留空）<input type="datetime-local" value={state.reference} disabled={disabled} onChange={e=>state.setReference(e.target.value)}/></label></div>}
  {state.error&&<p role="alert">{state.error}</p>}
  <div className="chat-attachment-menu" ref={container}>
   <button className="workspace-text-button" type="button" disabled={disabled} aria-haspopup="menu" aria-expanded={menu} onClick={()=>setMenu(v=>!v)}><Paperclip size={16}/>附件</button>
   {menu&&<div role="menu" aria-label="添加附件"><button type="button" role="menuitem" onClick={()=>{setMenu(false);file.current?.click()}}>图片识别作业</button><button type="button" role="menuitem" onClick={()=>{setMenu(false);window.dispatchEvent(new CustomEvent('campus-start-import',{detail:{method:'school'}}))}}>导入课表</button></div>}
   <input ref={file} hidden aria-label="选择作业截图" type="file" accept={IMAGE_TYPES.join(',')} onChange={e=>{if(e.target.files?.length)void state.add(Array.from(e.target.files));e.target.value=''}}/>
  </div>
 </>;
}
