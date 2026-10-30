import {useEffect,useRef,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import { X } from 'lucide-react';

// Panels can close out of order when a native navigation event changes pages.
const activePanels = new Map<symbol,{panel:HTMLDivElement;overlay:HTMLDivElement}>();
let originalInert = false;
function syncPanels() {
  const entries=[...activePanels.values()];
  entries.forEach(({panel,overlay},index)=>{
    panel.inert=index!==entries.length-1;
    panel.setAttribute('aria-hidden',String(panel.inert));
    overlay.style.zIndex=String(50+index*2);
    panel.style.zIndex=String(51+index*2);
  });
}

export function DetailPanel({open,title,heading,onClose,children,footer}:{open:boolean;title:string;heading?:string;onClose:()=>void;children:ReactNode;footer?:ReactNode}) {
  const panel=useRef<HTMLDivElement>(null),overlay=useRef<HTMLDivElement>(null),close=useRef(onClose);
  close.current=onClose;
  useEffect(()=>{
    if(!open)return;
    const previous=document.activeElement as HTMLElement|null;
    const shell=document.querySelector<HTMLElement>('.workspace-shell');
    const token=Symbol('detail-panel');
    if(activePanels.size===0)originalInert=shell?.inert??false;
    activePanels.set(token,{panel:panel.current!,overlay:overlay.current!});
    syncPanels();
    if(shell)shell.inert=true;
    const frame=requestAnimationFrame(()=>panel.current?.querySelector<HTMLElement>('button,input,textarea,select')?.focus());
    const keydown=(event:KeyboardEvent)=>{
      if([...activePanels.keys()].at(-1)!==token||document.querySelector('[role="dialog"][data-state="open"]:not(.detail-panel)'))return;
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close.current();}
      if(event.key==='Tab') {
        const controls=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]')??[]).filter(node=>node.getClientRects().length);
        const first=controls[0],last=controls.at(-1);
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    };
    document.addEventListener('keydown',keydown,true);
    return ()=>{cancelAnimationFrame(frame);document.removeEventListener('keydown',keydown,true);activePanels.delete(token);panel.current?.removeAttribute('aria-hidden');if(panel.current)panel.current.inert=false;syncPanels();if(shell)shell.inert=activePanels.size>0||originalInert;if(previous?.isConnected&&!previous.closest('[hidden]'))previous.focus();};
  },[open]);
  return createPortal(<div className="detail-host" hidden={!open}>
      <div ref={overlay} className="dialog-overlay detail-overlay" onClick={()=>close.current()} aria-hidden="true"/>
      <div ref={panel} className="detail-panel" role="dialog" aria-modal="true" aria-label={title}>
        <header><h2>{heading??title}</h2><button type="button" onClick={()=>close.current()} aria-label={`关闭${title}`}><X size={20}/></button></header>
        <div className="detail-panel-content">{children}</div>
        {footer&&<footer>{footer}</footer>}
      </div>
  </div>,document.body);
}
