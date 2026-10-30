import {useEffect,useState} from 'react';
import {DetailPanel} from './layout/DetailPanel';
import {Button} from './components/ui/button';

export function ReminderLinkPanel(){
  const [link,setLink]=useState<{title:string;url:string}|null>(null),[open,setOpen]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{
    const listener=(event:Event)=>{
      const value=(event as CustomEvent).detail;
      try {const url=new URL(value?.url);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)return;setLink({title:typeof value.title==='string'?value.title:'日程资料',url:url.href});setMessage('');setOpen(true);}catch{return;}
    };
    window.addEventListener('campus-web-reference',listener);return()=>window.removeEventListener('campus-web-reference',listener);
  },[]);
  return <DetailPanel open={open} title={link?.title??'日程资料'} onClose={()=>setOpen(false)}><label>资料链接<input readOnly value={link?.url??''} onFocus={event=>event.target.select()}/></label><Button variant="outline" onClick={async()=>{try{await navigator.clipboard.writeText(link?.url??'');setMessage('已复制链接。');}catch{setMessage('请选中链接并手工复制。');}}}>复制链接</Button>{message&&<p role="status">{message}</p>}</DetailPanel>;
}
