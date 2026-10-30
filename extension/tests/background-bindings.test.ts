import {beforeEach,expect,it,vi} from 'vitest';
const h=vi.hoisted(()=>({handlers:{} as Record<string,(request:any)=>Promise<any>>,bindings:{} as Record<string,any>,onRemoved:null as any}));
vi.mock('../lib/protocol',()=>({onMessage:(name:string,fn:any)=>{h.handlers[name]=fn;}}));
vi.mock('../lib/build-config',()=>({appOrigin:'http://127.0.0.1:5173',adapter:{school_origin:'https://fixture.scut.edu.cn',entry_url:'https://fixture.scut.edu.cn/',route_pattern:'.*'}}));
vi.mock('wxt/browser',()=>({browser:{storage:{session:{get:async()=>({bindings:structuredClone(h.bindings)}),set:async(value:any)=>{h.bindings=structuredClone(value.bindings);}}},tabs:{create:async()=>({id:200,windowId:1}),update:async()=>({windowId:1}),get:async()=>({url:'https://fixture.scut.edu.cn/'}),onRemoved:{addListener:(fn:any)=>{h.onRemoved=fn;}}},windows:{update:async()=>{}},alarms:{create:async()=>{},clear:async()=>{},onAlarm:{addListener:()=>{}}}}}));
vi.stubGlobal('defineBackground',(fn:any)=>fn);
const initialize=(await import('../entrypoints/background')).default as unknown as ()=>void;
function invoke(name:string,request:any){const handler=h.handlers[name];if(!handler)throw new Error('Missing message handler: '+name);return handler(request);}
const id='7d6ace42-e846-4eba-a704-4fa16c40d076',owner='fixture-owner';
const sender=(tab:number)=>({frameId:0,tab:{id:tab,url:'http://127.0.0.1:5173/school-import/'+id}});
const data=(generation:string)=>({sessionId:id,owner,nonce:'fixture-nonce',bindingGeneration:generation,expiresAt:new Date(Date.now()+60_000).toISOString()});
beforeEach(()=>{h.handlers={};h.bindings={};initialize();});
it('old bridge cleanup and restore cannot erase or take over a newer binding generation',async()=>{
  await invoke('start',{data:data('old'),sender:sender(81)});
  await invoke('start',{data:data('new'),sender:sender(82)});
  expect(await invoke('restore',{data:data('old'),sender:sender(81)})).toBeNull();
  await invoke('stop',{data:data('old'),sender:sender(81)});
  expect(h.bindings[id].bindingGeneration).toBe('new');expect(h.bindings[id].appTab).toBe(82);
  await invoke('stop',{data:data('new'),sender:sender(82)});
  expect(h.bindings).toEqual({});
  expect(await invoke('binding',{sender:{frameId:0,tab:{id:200,url:'https://fixture.scut.edu.cn/'}}})).toBeNull();
});
