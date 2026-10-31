import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import {nativeImport} from './native-import';
import {Button} from './components/ui/button';
import type {Resource} from './types';

export function ExtensionSetup({visible}:{visible:boolean}){
 const [expanded,setExpanded]=useState(false),[feedback,setFeedback]=useState(''),[busy,setBusy]=useState(false);
 const mode=useQuery({queryKey:['app-mode'],queryFn:()=>api<{mode:string}>('/app-mode')});
 const installation=useQuery({queryKey:['extension-installation'],queryFn:()=>api<{directory?:string;available?:boolean;version?:string}>('/local/extension-installation'),enabled:visible&&mode.data?.mode==='local'});
 const sessions=useQuery({queryKey:['browser-imports'],queryFn:()=>api<Resource[]>('/browser-imports'),refetchInterval:visible?2000:false});
 const latest=sessions.data?.at(-1),state=latest?.data.desktop_bridge_status;
 useEffect(()=>{if(state==='extension_missing'||state==='extension_outdated')setExpanded(true);},[state,latest?.id]);
 async function action(run:()=>Promise<unknown>,message:string){if(busy)return;setBusy(true);setFeedback('');try{await run();setFeedback(message);}catch(e){setFeedback(String(e));}finally{setBusy(false)}}
 return <details className="import-extension-guide" open={expanded} onToggle={e=>setExpanded(e.currentTarget.open)}><summary>首次使用：安装课表扩展</summary>
  <div className="extension-setup">
   {state==='ready'?<p role="status">扩展已连接，可以继续导入。</p>:<p>只需设置一次。请在上方所选的浏览器完成安装。</p>}
   <ol><li><strong>打开扩展管理页</strong><p>开启右上角的“开发者模式”。</p><Button variant="outline" disabled={busy} onClick={()=>void action(()=>nativeImport('open-extension-manager'),'已请求打开所选浏览器的扩展管理页。若未打开，请手动输入 chrome://extensions 或 edge://extensions。')}>打开扩展管理页</Button></li>
   <li><strong>加载课表扩展</strong><p>点击“加载已解压的扩展”，选择下方固定目录。</p><Button variant="outline" disabled={busy} onClick={()=>void action(()=>api('/local/open-extension-folder',{method:'POST',body:'{}'}),'扩展目录已打开。')}>打开扩展目录</Button><Button variant="outline" disabled={busy} onClick={()=>void action(()=>nativeImport('copy-extension-path'),'已复制扩展路径，可在文件选择窗口按 ⌘⇧G 后粘贴。')}>复制扩展路径</Button>
   {installation.data?.directory&&<p className="directory">{installation.data.directory}</p>}{installation.data?.available===false&&<p role="alert">扩展文件未准备好，请重新安装完整App。</p>}</li>
   <li><strong>回到导入浏览器页</strong><p>安装后刷新该页，软件会自动检测并继续。扩展更新时在扩展管理页点击“重新加载”，再刷新导入页。</p></li></ol>
   {state==='extension_outdated'&&<p role="alert">扩展版本过旧，请加载App提供的新版目录并重新加载。</p>}
   {installation.data?.version&&<small>内置扩展 {installation.data.version}</small>}{feedback&&<p role="status">{feedback}</p>}
  </div>
 </details>;
}
