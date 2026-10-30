import {useEffect,useState} from 'react';
import {api} from './api';
import type {Resource} from './types';
import {extension} from './BrowserImport';
import {Button} from './components/ui/button';

const importId=/^\/school-import\/([a-f0-9-]{36})$/.exec(location.pathname)?.[1];
const grant=importId?new URLSearchParams(location.hash.slice(1)).get('grant'):null;
if(importId)history.replaceState(null,'',location.pathname);
type View={phase:'connecting'|'missing'|'waiting'|'returned'|'error';text:string};
let view:View={phase:'connecting',text:'正在连接课表扩展…'},running=false;
const listeners=new Set<(value:View)=>void>();
function publish(value:View){view=value;listeners.forEach(listener=>listener(value));}
const headers=()=>({'Authorization':'Bearer '+grant});
async function runBridge(){
  if(running)return;
  running=true;publish({phase:'connecting',text:'正在连接课表扩展…'});
  try {
    if(!importId||!grant||!/^[a-f0-9-]{36}\.[a-f0-9]{64}$/.test(grant))throw new Error('导入授权不可用，请回App重新发起。');
    const path='/desktop-import-bridge/'+importId;
    let value=await api<{session:Resource;owner_id:string}>(path,{headers:headers()});
    if(['preview_ready','completed'].includes(value.session.data.status)){publish({phase:'returned',text:'已回传，请回App校对。'});return;}
    try {await extension('detect');}
    catch {
      await api(path+'/bridge-state',{method:'POST',headers:headers(),body:JSON.stringify({state:'extension_missing'})});
      publish({phase:'missing',text:'未检测到课表扩展。请在这个浏览器安装或启用扩展，再重新检测。'});return;
    }
    await api(path+'/bridge-state',{method:'POST',headers:headers(),body:JSON.stringify({state:'ready'})});
    await extension('start',{sessionId:importId,owner:value.owner_id,expiresAt:value.session.data.expires_at});
    publish({phase:'waiting',text:'请本人登录学校，进入个人课表并查询学期。'});
    const captureKey=crypto.randomUUID();
    while(Date.now()<Date.parse(value.session.data.expires_at)) {
      value=await api(path,{headers:headers()});
      let session=value.session;
      if(['preview_ready','completed'].includes(session.data.status)) {
        try {await extension('stop',{sessionId:importId,owner:value.owner_id});}catch { /* the App owns the authoritative result */ }
        publish({phase:'returned',text:'已回传，请回App校对。'});return;
      }
      const binding=await extension('restore',{sessionId:importId,owner:value.owner_id});
      if(!binding)throw new Error('扩展会话已结束，请回App重试。');
      const order=['queued','waiting_login','waiting_timetable','extracting','preview_ready'];
      for(const event of binding.events??[]) {
        const desired=event.kind==='opened'?'waiting_login':event.kind;
        if(event.kind!=='failed'&&order.indexOf(session.data.status)>=order.indexOf(desired))continue;
        session=await api<Resource>(path+'/events',{method:'POST',headers:{...headers(),'Idempotency-Key':event.event_id},body:JSON.stringify({...event,revision:session.revision})});
        if(session.data.status==='failed')throw new Error('学校页面已关闭或采集失败，请回App重试。');
      }
      if(binding.capture&&session.data.status==='extracting') {
        await api(path+'/capture',{method:'POST',headers:{...headers(),'Idempotency-Key':captureKey},body:JSON.stringify({...binding.capture,revision:session.revision,adapter_version:session.data.adapter_version,school_origin:new URL(session.data.entry_url).origin})});
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    throw new Error('导入已过期，请回App重新发起。');
  } catch(error) {publish({phase:'error',text:String(error)});}
  finally {running=false;}
}

export function SchoolImportBridge(){
  const [state,setState]=useState(view);
  useEffect(()=>{listeners.add(setState);setState(view);void runBridge();return()=>{listeners.delete(setState);};},[]);
  return <main className="school-import-bridge"><h1>学校课表导入</h1><p role={state.phase==='error'?'alert':'status'}>{state.text}</p>
    {['missing','error'].includes(state.phase)&&<Button onClick={()=>void runBridge()}>重新检测</Button>}
    <p>课程校对和保存请在课间App中完成。</p>
  </main>;
}
