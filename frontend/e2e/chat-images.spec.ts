import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
const file=(name='homework')=>new URL('./fixtures/chat-images/'+name+'.png',import.meta.url);
async function enter(page:Page){
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`images-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');
 await page.getByRole('button',{name:'注册并登录'}).click();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();
 await expect(page.getByLabel('给助手的消息')).toBeVisible();
}
async function choose(page:Page,name='homework'){
 await page.getByRole('button',{name:'附件',exact:true}).click();
 await expect(page.getByRole('menuitem')).toHaveText(['图片识别作业','课程资料','导入课表']);
 await page.getByLabel('选择作业截图').setInputFiles({name:name+'.png',mimeType:'image/png',buffer:readFileSync(file(name))});
 await page.keyboard.press('Escape');
 await expect(page.getByAltText('待发送的作业截图')).toBeVisible();
}
async function send(page:Page){
 await page.getByRole('button',{name:'发送',exact:true}).click();
}
test('image-only chat identifies two items, corrects original, explicitly saves and replays image history',async({page})=>{
 await enter(page);let uploads=0;page.on('request',r=>{if(r.url().endsWith('/api/assets')&&r.method()==='POST')uploads++});
 await choose(page);expect(uploads).toBe(0);await expect(page.getByRole('checkbox')).toHaveCount(0);await expect(page.locator('input[type=datetime-local]')).toHaveCount(0);await expect(page.getByRole('button',{name:'发送',exact:true})).toBeEnabled();await send(page);
 const review=page.getByRole('region',{name:'对话作业草稿'});
 await expect(review).toBeVisible();await review.getByText('校对详情',{exact:true}).click();
 await expect(review.getByRole('heading',{name:'核对原图和识别结果'})).toBeVisible();
 await expect.poll(()=>review.getByRole('textbox',{name:'标题',exact:true}).evaluateAll(nodes=>nodes.map(n=>(n as HTMLInputElement).value))).toEqual(['高数作业','英语作业']);
 expect(await page.request.get('/api/tasks').then(r=>r.json())).toEqual([]);
 await page.getByLabel('给助手的消息').fill('修改第二项为英语听力');await expect(page.locator('.composer-bottom button')).toBeEnabled();await page.getByLabel('给助手的消息').press('Enter');
 await expect.poll(()=>review.getByRole('textbox',{name:'标题',exact:true}).evaluateAll(nodes=>nodes.map(n=>(n as HTMLInputElement).value))).toEqual(['高数作业','英语听力']);
 await expect(review.getByAltText('待校对的作业原图')).toBeVisible();
 await review.getByRole('button',{name:'确认保存',exact:true}).click();
 await expect.poll(()=>page.request.get('/api/tasks').then(r=>r.json()).then(x=>x.length)).toBe(2);
 await page.reload();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();
 await expect(page.locator('.message.user img').first()).toBeVisible();expect(uploads).toBe(1);
});
test('drop and paste append previews, reject excess batches and preserve text paste',async({page})=>{
 await enter(page);let uploads=0;page.on('request',r=>{if(r.url().endsWith('/api/assets')&&r.method()==='POST')uploads++});
 const bytes=Array.from(readFileSync(file()));
 await page.evaluate(bytes=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(bytes)],'拖入.png',{type:'image/png'}));document.querySelector('[data-testid=chat-image-drop]')!.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}))},bytes);
 await expect(page.getByText('拖入.png',{exact:true})).toBeVisible();
 await page.evaluate(bytes=>{const dt=new DataTransfer();for(const name of ['一.png','二.png','三.png','四.png','五.png','六.png'])dt.items.add(new File([new Uint8Array(bytes)],name,{type:'image/png'}));document.querySelector('[data-testid=chat-image-drop]')!.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}))},bytes);
 await expect(page.getByRole('alert')).toContainText('5');await expect(page.getByText('拖入.png',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:/移除.*拖入/}).click();
 await page.evaluate(bytes=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(bytes)],'粘贴.png',{type:'image/png'}));document.querySelector('textarea[aria-label="给助手的消息"]')!.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}))},bytes);
 await expect(page.getByText('粘贴.png',{exact:true})).toBeVisible();expect(uploads).toBe(0);
 const textPasteAllowed=await page.evaluate(()=>{const dt=new DataTransfer();dt.setData('text/plain','普通文字');const e=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});document.querySelector('textarea[aria-label="给助手的消息"]')!.dispatchEvent(e);return !e.defaultPrevented});
 expect(textPasteAllowed).toBe(true);
 await page.getByLabel('选择作业截图').setInputFiles({name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('text')});
 await expect(page.getByRole('alert')).toContainText('仅支持');await expect(page.getByText('粘贴.png',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'新会话',exact:true}).click();await expect(page.getByAltText('待发送的作业截图')).toHaveCount(0);
});
test('failed vision retries same run, cancelling vision leaves no actionable draft',async({page})=>{
 await enter(page);await choose(page,'retry');await send(page);
 await expect(page.getByRole('button',{name:'重试图片识别'})).toBeVisible();await page.getByRole('button',{name:'重试图片识别'}).click();
 await expect(page.getByRole('region',{name:'对话作业草稿'})).toBeVisible();
 await page.getByRole('button',{name:'新会话',exact:true}).click();
 await expect(page.getByRole('heading',{name:'核对原图和识别结果'})).toHaveCount(0);
 await choose(page,'cancel');await send(page);await expect(page.getByRole('button',{name:'取消图片识别'})).toBeVisible();await page.getByRole('button',{name:'取消图片识别'}).click();
 await expect(page.getByText('已取消识别',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'核对原图和识别结果'})).toHaveCount(0);
});


test('a delayed image retry response cannot take ownership of a new conversation',async({page})=>{
 await enter(page);await choose(page,'retry-late');await send(page);
 await expect(page.getByRole('button',{name:'重试图片识别'})).toBeVisible();
 let held=false,release!:()=>void;const released=new Promise<void>(resolve=>release=resolve);
 await page.route('**/api/agent/runs/*/image/retry',async route=>{const response=await route.fetch();held=true;await released;await route.fulfill({response})});
 await page.getByRole('button',{name:'重试图片识别'}).click();await expect.poll(()=>held).toBe(true);
 await page.getByRole('button',{name:'新会话',exact:true}).click();release();
 await expect(page.getByRole('heading',{name:'核对原图和识别结果'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'重试图片识别'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'新会话',exact:true})).toBeEnabled();
});

test('received streaming text remains visible when WebKit animation frames are suspended',async({page})=>{
 await enter(page);
 const rid='suspended-stream';let tid='';
 await page.route('**/api/agent/runs',async route=>{tid=route.request().postDataJSON().thread_id;await route.fulfill({json:{id:rid,kind:'agent_run',revision:3,data:{thread_id:tid,status:'running',event_counter:2}}})});
 await page.route('**/api/agent/runs/'+rid,route=>route.fulfill({json:{id:rid,kind:'agent_run',revision:3,data:{thread_id:tid,status:'running',event_counter:2}}}));
 await page.route('**/api/agent/runs/'+rid+'/events?*',route=>{
  const after=Number(new URL(route.request().url()).searchParams.get('after'));
  const events=[{run_id:rid,seq:1,type:'message',payload:{role:'user',message_id:'s-user',content:'frame-test'}},{run_id:rid,seq:2,type:'message_delta',payload:{message_id:'s-assistant',delta:'首段已到达'}}];
  return route.fulfill({contentType:'text/event-stream',body:events.filter(e=>e.seq>after).map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')||': keepalive\n\n'});
 });
 await page.evaluate(()=>{window.requestAnimationFrame=()=>0});
 await page.getByLabel('给助手的消息').fill('frame-test');await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect(page.locator('.message.assistant')).toContainText('首段已到达');
});

test('multiple screenshots append at top left and save together without deadlines or a right review panel',async({page})=>{
 await enter(page);let uploads=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/assets'))uploads++});
 await choose(page);await page.getByLabel('选择作业截图').setInputFiles({name:'第二张.png',mimeType:'image/png',buffer:readFileSync(file('homework'))});
 await expect(page.locator('.composer img')).toHaveCount(2);
 expect(uploads).toBe(0);await expect(page.locator('.composer input[type=checkbox],.composer input[type=datetime-local]')).toHaveCount(0);
 const boxes=await page.locator('.composer img').evaluateAll(ns=>ns.map(n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y}}));expect(boxes[0].x).toBeLessThan(boxes[1].x);expect(Math.abs(boxes[0].y-boxes[1].y)).toBeLessThan(3);
 await page.getByRole('heading',{name:'助手',exact:true}).click();
 await page.screenshot({path:'../docs/validation/demo2.6.1/chat-images-before-send.png',fullPage:true});
 await send(page);
 const review=page.getByRole('region',{name:'对话作业草稿'});
 await expect(review).toBeVisible();await expect(page.locator('.assistant-layout.has-review')).toHaveCount(0);
 const drafts=await page.request.get('/api/drafts').then(r=>r.json());const d=drafts.find((x:any)=>x.data.draft_kind==='assignment');
 expect(d.data.payload.asset_ids).toHaveLength(2);expect(d.data.payload.items).toHaveLength(4);
 expect(d.data.payload.items.every((i:any)=>i.due_at===null)).toBe(true);
 await expect(review.getByRole('button',{name:'暂不填写',exact:true})).toBeEnabled();await review.getByRole('button',{name:'暂不填写',exact:true}).click();
 await expect.poll(()=>page.request.get('/api/drafts').then(r=>r.json()).then(ds=>ds.find((x:any)=>x.id===d.id)?.data.source.deadline_followup)).toBe('deferred');
 await expect(review.getByText('截止日期先留空，之后可以补充。',{exact:true})).toBeVisible();
 await page.screenshot({path:'../docs/validation/demo2.6.1/chat-images-inline-review.png',fullPage:true});
 await review.getByRole('button',{name:'确认保存 4 项',exact:true}).click();
 await expect.poll(()=>page.request.get('/api/tasks').then(r=>r.json()).then(ts=>ts.length)).toBe(4);
 const tasks=await page.request.get('/api/tasks').then(r=>r.json());expect(tasks.every((t:any)=>t.data.due_at===null)).toBe(true);
 expect(new Set(tasks.map((t:any)=>t.data.asset_id)).size).toBe(2);
 await page.reload();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();await expect(page.locator('.message.user img')).toHaveCount(2);expect(uploads).toBe(2);
});

test('chat fills only the explicitly answered task deadline, leaving the other optional',async({page})=>{
 await enter(page);await choose(page);await send(page);const review=page.getByRole('region',{name:'对话作业草稿'});await expect(review).toBeVisible();
 await expect.poll(()=>page.request.get('/api/agent/threads').then(r=>r.json()).then(async ts=>Promise.all(ts.map((t:any)=>page.request.get(`/api/agent/threads/${t.id}/runs`).then(r=>r.json())))).then(groups=>groups.flat().every((r:any)=>r.data.status==='done'))).toBe(true);
 await page.getByLabel('给助手的消息').fill('第一项2026年11月6日20:00，第二项暂不填');await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect.poll(()=>page.request.get('/api/drafts').then(r=>r.json()).then(ds=>ds.find((d:any)=>d.data.draft_kind==='assignment').data.payload.items[0].due_at)).toBe('2026-11-06T20:00:00+08:00');
 const draft=(await page.request.get('/api/drafts').then(r=>r.json())).find((d:any)=>d.data.draft_kind==='assignment');expect(draft.data.payload.items[1].due_at).toBeNull();
 await review.getByRole('button',{name:'确认保存 2 项',exact:true}).click();await expect.poll(()=>page.request.get('/api/tasks').then(r=>r.json()).then(ts=>ts.length)).toBe(2);
});

test('a pending image decode cannot append to a new conversation',async({page})=>{
 await enter(page);
 await page.evaluate(()=>{const Original=window.Image;const descriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src')!;(window as any).releaseImageLoads=[];(window as any).Image=function(){const img=new Original();Object.defineProperty(img,'src',{set(value){(window as any).releaseImageLoads.push(()=>descriptor.set!.call(img,value));}});return img;};});
 await page.getByLabel('选择作业截图').setInputFiles({name:'迟到的图片.png',mimeType:'image/png',buffer:readFileSync(file())});
 await expect.poll(()=>page.evaluate(()=>(window as any).releaseImageLoads.length)).toBe(1);
 await page.getByRole('button',{name:'新会话',exact:true}).click();
 await page.evaluate(()=>{(window as any).releaseImageLoads.splice(0).forEach((release:()=>void)=>release());});
 await expect(page.locator('.composer img')).toHaveCount(0);
 await expect(page.getByLabel('选择作业截图')).toBeEnabled();
 await page.getByLabel('选择作业截图').setInputFiles({name:'新会话图片.png',mimeType:'image/png',buffer:readFileSync(file())});
 await expect.poll(()=>page.evaluate(()=>(window as any).releaseImageLoads.length)).toBe(1);
 await page.evaluate(()=>{(window as any).releaseImageLoads.splice(0).forEach((release:()=>void)=>release());});
 await expect(page.getByText('新会话图片.png',{exact:true})).toBeVisible();await expect(page.getByText('迟到的图片.png',{exact:true})).toHaveCount(0);
});
