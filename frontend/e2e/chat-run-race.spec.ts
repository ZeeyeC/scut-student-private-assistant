import {test,expect} from '@playwright/test';

test('an older run status arriving during a new reply never clears busy state',async({page})=>{
 let posts=0,held=false,oldDelivered=false,finishSecond=false;
 let allowFirst!:()=>void,releaseOld!:()=>void;
 const firstCreated=new Promise<void>(r=>allowFirst=r),oldReleased=new Promise<void>(r=>releaseOld=r);
 const resource=(id:string,status:string)=>({id,kind:'agent_run',revision:1,data:{status,event_counter:id==='race-first'?3:4}});
 const event=(run_id:string,seq:number,type:string,payload:object)=>`data: ${JSON.stringify({run_id,seq,type,payload})}\n\n`;
 await page.route('**/api/agent/runs',async route=>{
  if(route.request().method()!=='POST')return route.continue();
  posts++;const id=posts===1?'race-first':'race-second';allowFirst();await route.fulfill({json:resource(id,'queued')});
 });
 await page.route('**/api/agent/threads/*/runs',async route=>{await firstCreated;await route.fulfill({json:[resource('race-first','running')]});});
 await page.route(/\/api\/agent\/runs\/race-(first|second)\/events\?/,async route=>{
  const url=new URL(route.request().url()),id=url.pathname.includes('race-first')?'race-first':'race-second',after=Number(url.searchParams.get('after'));
  const frames=id==='race-first'?[[1,'message',{role:'user',message_id:'a-user',content:'first'}],[2,'message',{role:'assistant',message_id:'a',content:'第一段第二段'}],[3,'done',{}]]:
   [[1,'message',{role:'user',message_id:'b-user',content:'second'}],[2,'message_delta',{message_id:'b',delta:'第一段'}],...(finishSecond?[[3,'message_delta',{message_id:'b',delta:'第二段'}],[4,'done',{}]]:[])];
  await route.fulfill({contentType:'text/event-stream',body:frames.filter(row=>Number(row[0])>after).map(row=>event(id,Number(row[0]),String(row[1]),row[2] as object)).join('')||': keepalive\n\n'});
 });
 await page.route(/\/api\/agent\/runs\/race-(first|second)$/,async route=>{
  if(route.request().url().endsWith('race-first')){held=true;await oldReleased;await route.fulfill({json:resource('race-first','done')});oldDelivered=true;}
  else await route.fulfill({json:resource('race-second',finishSecond?'done':'running')});
 });
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`chat-race-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');await page.getByRole('button',{name:'注册并登录'}).click();
 await page.getByRole('button',{name:'助手',exact:true}).click();const composer=page.getByLabel('给助手的消息');
 await composer.fill('first');await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect(page.locator('.message.assistant').first()).toContainText('第一段第二段');await expect.poll(()=>held).toBe(true);
 await expect(page.getByRole('button',{name:'新会话',exact:true})).toBeEnabled();
 await composer.fill('second');await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect.poll(()=>posts).toBe(2);await expect(page.locator('.message.assistant').nth(1)).toContainText('第一段');
 releaseOld();await expect.poll(()=>oldDelivered).toBe(true);
 await expect(page.getByRole('button',{name:'新会话',exact:true})).toBeDisabled({timeout:800});
 finishSecond=true;await expect(page.locator('.message.assistant').nth(1)).toContainText('第一段第二段');
 await expect(page.getByRole('button',{name:'新会话',exact:true})).toBeEnabled();
});
