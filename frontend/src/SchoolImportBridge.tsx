import {useEffect,useState} from 'react';
import {api,ApiError} from './api';
import type {Resource} from './types';
import {extension} from './BrowserImport';
import {Button} from './components/ui/button';

const importId=/^\/school-import\/([a-f0-9-]{36})$/.exec(location.pathname)?.[1];
const grantKey=importId?'campus-import-grant:'+importId:'';
const suppliedGrant=importId?new URLSearchParams(location.hash.slice(1)).get('grant'):null;
let grant=suppliedGrant;
if(importId){
  try{
    if(suppliedGrant&&/^[a-f0-9-]{36}\.[a-f0-9]{64}$/.test(suppliedGrant))sessionStorage.setItem(grantKey,suppliedGrant);
    if(suppliedGrant===null)grant=sessionStorage.getItem(grantKey);
  }catch{/* A blocked tab store still permits the original one-shot import. */}
  history.replaceState(null,'',location.pathname);
}
function forgetGrant(){try{sessionStorage.removeItem(grantKey);}catch{/* No persistent storage is required. */}}
type View={phase:'connecting'|'missing'|'waiting'|'returned'|'error';text:string};
let view:View={phase:'connecting',text:'正在连接课表扩展…'},running=false;
const listeners=new Set<(value:View)=>void>();
function publish(value:View){view=value;listeners.forEach(listener=>listener(value));}
const headers=()=>({'Authorization':'Bearer '+grant});
async function runBridge(){
  if(running)return;
  let binding:{sessionId:string;owner:string;expiresAt:string;bindingGeneration:string}|undefined;
  running=true;publish({phase:'connecting',text:'正在连接课表扩展…'});
  try {
    if(!importId||!grant||!/^[a-f0-9-]{36}\.[a-f0-9]{64}$/.test(grant))throw new Error('导入授权不可用，请回App重新发起。');
    const path='/desktop-import-bridge/'+importId;
    let value=await api<{session:Resource;owner_id:string}>(path,{headers:headers()});
    if(['preview_ready','completed'].includes(value.session.data.status)){forgetGrant();publish({phase:'returned',text:'已回传，请回App校对。'});return;}
    let needsUpdate=false;
    try {const detected=await extension('detect');if(!detected?.capabilities?.includes('scoped-bindings-v1')){needsUpdate=true;throw new Error('扩展需要更新');}}
    catch {
      await api(path+'/bridge-state',{method:'POST',headers:headers(),body:JSON.stringify({state:needsUpdate?'extension_outdated':'extension_missing'})});
      publish({phase:'missing',text:needsUpdate?'扩展需要更新。请加载App提供的新版扩展，重新加载后刷新本页。':'未检测到课表扩展。请在这个浏览器安装或启用扩展，再刷新本页；本页也会自动重新检测。'});return;
    }
    await api(path+'/bridge-state',{method:'POST',headers:headers(),body:JSON.stringify({state:'ready'})});
    binding={sessionId:importId,owner:value.owner_id,expiresAt:value.session.data.expires_at,bindingGeneration:crypto.randomUUID()};
    await extension('start',binding);
    publish({phase:'waiting',text:'请本人登录学校，进入个人课表并查询学期。'});
    const captureKey=crypto.randomUUID();
    while(Date.now()<Date.parse(value.session.data.expires_at)) {
      value=await api(path,{headers:headers()});
      let session=value.session;
      if(['preview_ready','completed'].includes(session.data.status)) {
        forgetGrant();publish({phase:'returned',text:'已回传，请回App校对。'});return;
      }
      const restored=await extension('restore',binding);
      if(!restored)throw new Error('扩展会话已结束，请回App重试。');
      const order=['queued','waiting_login','waiting_timetable','extracting','preview_ready'];
      for(const event of restored.events??[]) {
        const desired=event.kind==='opened'?'waiting_login':event.kind;
        if(event.kind!=='failed'&&order.indexOf(session.data.status)>=order.indexOf(desired))continue;
        session=await api<Resource>(path+'/events',{method:'POST',headers:{...headers(),'Idempotency-Key':event.event_id},body:JSON.stringify({...event,revision:session.revision})});
        if(session.data.status==='failed')throw new Error('学校页面已关闭或采集失败，请回App重试。');
      }
      if(restored.capture&&session.data.status==='extracting') {
        await api(path+'/capture',{method:'POST',headers:{...headers(),'Idempotency-Key':captureKey},body:JSON.stringify({...restored.capture,revision:session.revision,adapter_version:session.data.adapter_version,school_origin:new URL(session.data.entry_url).origin})});
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    forgetGrant();throw new Error('导入已过期，请回App重新发起。');
  } catch(error) {if(error instanceof ApiError&&[401,403,404,410].includes(error.status))forgetGrant();publish({phase:'error',text:String(error)});}
  finally {
    if(binding){try{await extension('stop',binding);}catch{/* Binding has a finite expiry if the extension is unavailable. */}}
    running=false;
  }
}

export function SchoolImportBridge(){
  const [state,setState]=useState(view);
  useEffect(()=>{listeners.add(setState);setState(view);void runBridge();const timer=setInterval(()=>{if(view.phase==='missing'&&document.visibilityState==='visible')void runBridge();},5000);return()=>{clearInterval(timer);listeners.delete(setState);};},[]);
  return <main className="school-import-bridge"><h1>学校课表导入</h1><p role={state.phase==='error'?'alert':'status'}>{state.text}</p>
    {['missing','error'].includes(state.phase)&&<Button onClick={()=>void runBridge()}>重新检测</Button>}
    <p>课程校对和保存请在课间App中完成。</p>
  </main>;
}
