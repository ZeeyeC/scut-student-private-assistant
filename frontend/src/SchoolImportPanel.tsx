import {useEffect,useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {Button} from './components/ui/button';
import {nativeImport,type BrowserSettings} from './native-import';
import {Globe} from 'lucide-react';

export function ImportBrowserSettings({compact=false}:{compact?:boolean}={}){
  const [settings,setSettings]=useState<BrowserSettings>(),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{
    const read=()=>{if(window.__campusNative)void nativeImport<BrowserSettings>('get-browser').then(setSettings).catch(error=>setError(String(error)));};
    read();window.addEventListener('campus-native-ready',read);window.addEventListener('campus-import-browser-changed',read);
    return()=>{window.removeEventListener('campus-native-ready',read);window.removeEventListener('campus-import-browser-changed',read);};
  },[]);
  return <div className={`import-browser-setting${compact?' compact':''}`}><label>{!compact&&'课表导入浏览器'}<select aria-label="课表导入浏览器" value={settings?.browser??'chrome'} disabled={!settings||busy} onChange={async event=>{
    setBusy(true);setError('');
    try {setSettings(await nativeImport<BrowserSettings>('set-browser',{browser:event.target.value}));window.dispatchEvent(new Event('campus-import-browser-changed'));}
    catch(error){setError(String(error));}finally{setBusy(false);}
  }}><option value="chrome">Chrome</option><option value="edge">Edge</option></select></label>
    {settings&&!settings.installed&&<p role="status">未安装所选浏览器，请安装它或切换选择。</p>}
    {!settings&&!compact&&<p>浏览器选择在独立App内生效。</p>}{error&&<p role="alert">{error}</p>}
  </div>;
}

export const activeImportStatuses=['queued','waiting_login','waiting_timetable','extracting','preview_ready'];
export const importStatusLabels:Record<string,string>={queued:'等待浏览器和扩展连接',waiting_login:'请本人登录学校，进入个人课表并查询学期',waiting_timetable:'等待个人课表加载',extracting:'正在提取课表',preview_ready:'课表已回传，请在App校对',completed:'课表已保存',cancelled:'本次导入已取消',expired:'本次导入已过期',failed:'本次导入失败'};
export function SchoolImportContent({onRequireOpen}:{onRequireOpen:()=>void}){
  const q=useQueryClient(),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const pending=useRef<Resource|null>(null),gate=useRef(false);
  const openRef=useRef(onRequireOpen);openRef.current=onRequireOpen;
  const sessions=useQuery({queryKey:['browser-imports'],queryFn:()=>api<Resource[]>('/browser-imports'),refetchInterval:2000});
  const latest=sessions.data?.at(-1);
  useEffect(()=>{if(latest?.data.draft_id)void q.invalidateQueries({queryKey:['drafts']});},[q,latest?.data.draft_id,latest?.data.status]);
  useEffect(()=>{
    const show=()=>{setError('');openRef.current();};
    const agent=(event:Event)=>{pending.current=(event as CustomEvent<Resource>).detail;show();void q.invalidateQueries({queryKey:['browser-imports']});};
    window.addEventListener('campus-agent-import',agent);
    return()=>{window.removeEventListener('campus-agent-import',agent);};
  },[q]);
  async function start(){
    if(gate.current)return;gate.current=true;setBusy(true);setError('');
    try {
      const settings=await nativeImport<BrowserSettings>('get-browser');
      if(!settings.installed)throw new Error('未安装所选浏览器，请安装或切换。');
      const session=pending.current??[...(sessions.data??[])].reverse().find(s=>activeImportStatuses.includes(s.data.status)&&s.data.status!=='preview_ready')??await api<Resource>('/browser-imports',{method:'POST',body:JSON.stringify({school_id:'scut'})});
      pending.current=session;
      await nativeImport('open-school-import',{importId:session.id});pending.current=null;
      await q.invalidateQueries({queryKey:['browser-imports']});
    }catch(error){setError(String(error));}finally{gate.current=false;setBusy(false);}
  }
  return <section className="import-school-primary">
      <div className="import-school-heading"><Globe size={22}/><div><h3>从学校导入</h3><small>浏览器登录 · 回到 App 校对</small></div></div>
      <p>打开学校课表，登录后由扩展读取课程。</p>
      <div className="import-browser-controls"><ImportBrowserSettings compact/>{latest?.data.status!=='preview_ready'&&<Button disabled={busy} onClick={()=>void start()}>{busy?'正在打开…':'打开浏览器导入'}</Button>}</div>
      {latest&&<p className="import-status" role="status">{latest.data.desktop_bridge_status==='extension_missing'?'未检测到扩展，请安装或启用后重试。':importStatusLabels[latest.data.status]}</p>}
      {latest&&activeImportStatuses.includes(latest.data.status)&&<Button variant="outline" disabled={busy} onClick={async()=>{try{await api(`/browser-imports/${latest.id}/cancel`,{method:'POST',body:JSON.stringify({revision:latest.revision})});pending.current=null;await q.invalidateQueries();}catch(error){setError(String(error));}}}>取消导入</Button>}
      {error&&<p role="alert">{error}</p>}
  </section>;
}

export function SchoolExtensionGuide({visible}:{visible:boolean}){
 const [error,setError]=useState('');
 const mode=useQuery({queryKey:['app-mode'],queryFn:()=>api<{mode:string}>('/app-mode')});
 const installation=useQuery({queryKey:['extension-installation'],queryFn:()=>api<{directory?:string;available?:boolean}>('/local/extension-installation'),enabled:visible&&mode.data?.mode==='local'});
 return <details className="import-extension-guide"><summary>首次使用：安装课表扩展</summary><ol><li>在所选浏览器启用扩展开发者模式。</li><li>加载下方扩展目录。</li><li>回到此处开始导入。</li></ol>{installation.data?.directory&&<p className="directory">{installation.data.directory}</p>}<Button variant="outline" onClick={async()=>{try{await api('/local/open-extension-folder',{method:'POST',body:'{}'});}catch(e){setError(String(e));}}}>打开扩展目录</Button>{error&&<p role="alert">{error}</p>}</details>;
}
