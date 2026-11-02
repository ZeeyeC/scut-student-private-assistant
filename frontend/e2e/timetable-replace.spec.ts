import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';
async function enter(page:Page){
 await page.addInitScript(()=>{(window as any).__importCalls=[];(window as any).__campusNative={request:async(command:string,payload:any)=>{(window as any).__importCalls.push({command,payload});return {browser:'chrome',installed:true};}};});
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`replace-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');await page.getByRole('button',{name:'注册并登录',exact:true}).click();
 await expect(page.getByRole('navigation',{name:'主导航'})).toBeVisible();
}
async function seed(page:Page,browser=false){
 return page.evaluate(async(browser)=>{
  const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
  const post=async(path:string,body:any,method='POST')=>{const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});if(!r.ok)throw new Error(await r.text());return r.json();};
  const s=await(await fetch('/api/settings')).json();s.data={...s.data,week1_monday:'2026-10-26',week_count:25,periods:{1:{start:'09:00',end:'10:00'}}};await post('/settings',s,'PUT');
  if(browser){
   let session=await post('/browser-imports',{school_id:'scut'});
   for(const kind of ['opened','waiting_timetable','extracting'])session=await post(`/browser-imports/${session.id}/events`,{event_id:crypto.randomUUID(),kind,revision:session.revision});
   await post(`/browser-imports/${session.id}/capture`,{revision:session.revision,adapter_version:session.data.adapter_version,school_origin:new URL(session.data.entry_url).origin,semester_label:'合成学校学期',fragments:['<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th></tr><tr><td>待重新导入</td><td>1</td><td>1-8</td><td>1</td></tr></table>']});return session.id;
  }
  const course=(key:string,name:string)=>({source_key:key,name,weekday:1,weeks:[1],periods:[1],campus:'大学城'});
  const old=await post('/drafts/timetable',{semester_label:'合成旧课表',courses:[course('old','旧课程')]});await post(`/drafts/${old.id}/confirm`,{revision:old.revision});
  const d=await post('/drafts/timetable',{semester_label:'合成新课表',courses:[course('new','新课程')]});
  const settings=await(await fetch('/api/settings')).json();settings.data.week_count=26;await post('/settings',settings,'PUT');return d.id;
 },browser);
}
async function open(page:Page){await page.getByRole('button',{name:'日程',exact:true}).click();await page.getByRole('button',{name:'导入课表',exact:true}).click();return page.getByRole('dialog',{name:'导入课表',exact:true});}
test('replacement previews deletions and recovers a concurrent settings change without losing edits',async({page})=>{
 await enter(page);await seed(page);const panel=await open(page);
 await panel.getByLabel('课程',{exact:true}).fill('已校对的新课程');
 const replace=panel.getByRole('checkbox',{name:'替换当前课表'});await expect(replace).not.toBeChecked();await replace.check();
 await panel.getByRole('button',{name:'校对完成，准备保存',exact:true}).click();await expect(panel).toContainText('将移除 1 条旧课程');
 await panel.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.9/覆盖保存确认.png',import.meta.url))});
 await replace.uncheck();await expect(panel.getByRole('button',{name:'确认保存',exact:true})).toHaveCount(0);await replace.check();
 await panel.getByRole('button',{name:'校对完成，准备保存',exact:true}).click();
 await page.evaluate(async()=>{const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;const s=await(await fetch('/api/settings')).json();s.data.week_count=27;await fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(s)});});
 const ack=panel.getByRole('checkbox',{name:'我已核对上述提示，仍按已确认的课程或事项保存'});if(await ack.count())await ack.check();
 await panel.getByRole('button',{name:'确认保存',exact:true}).click();await expect(panel).toContainText('已保留校对内容');await expect(panel.getByLabel('课程',{exact:true})).toHaveValue('已校对的新课程');
 expect((await(await page.request.get('/api/courses')).json())[0].data.name).toBe('旧课程');
 await panel.getByRole('button',{name:'校对完成，准备保存',exact:true}).click();if(await ack.count())await ack.check();await panel.getByRole('button',{name:'确认保存',exact:true}).click();
 await expect.poll(async()=> (await(await page.request.get('/api/courses')).json()).map((r:any)=>r.data.name)).toEqual(['已校对的新课程']);
});
test('returned school timetable can be restarted without saving or leaving its old draft actionable',async({page})=>{
 await enter(page);const previous=await seed(page,true);const panel=await open(page);
 await expect(panel).toContainText('待重新导入');await panel.getByRole('button',{name:'重新导入',exact:true}).click();
 await expect.poll(async()=> (await(await page.request.get(`/api/browser-imports/${previous}`)).json()).data.status).toBe('cancelled');
 await expect.poll(()=>page.evaluate(()=>(window as any).__importCalls.filter((c:any)=>c.command==='open-school-import').length)).toBe(1);
 expect(await(await page.request.get('/api/courses')).json()).toEqual([]);await expect(panel.getByLabel('课程',{exact:true})).toHaveCount(0);
 await expect(panel).toContainText('点击“查询”');
});
test('failed browser launch retries the new import instead of creating another replacement session',async({page})=>{
 await enter(page);await seed(page,true);const panel=await open(page);
 await page.evaluate(()=>{let first=true;const native=(window as any).__campusNative;const request=native.request;native.request=async(command:string,payload:any)=>{if(command==='open-school-import'&&first){first=false;throw new Error('模拟浏览器启动失败');}return request(command,payload);};});
 await panel.getByRole('button',{name:'重新导入',exact:true}).click();await expect(panel).toContainText('模拟浏览器启动失败');
 await panel.getByRole('button',{name:/^(重新导入|打开浏览器导入)$/}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).__importCalls.filter((c:any)=>c.command==='open-school-import').length)).toBe(1);
 expect(await(await page.request.get('/api/browser-imports')).json()).toHaveLength(2);
});
test('an expired pending launch is replaced on retry instead of reopening its terminal id',async({page})=>{
 await enter(page);await seed(page,true);const panel=await open(page);
 await page.evaluate(()=>{let first=true;const native=(window as any).__campusNative;const request=native.request;native.request=async(command:string,payload:any)=>{if(command==='open-school-import'&&first){first=false;throw new Error('模拟浏览器启动失败');}return request(command,payload);};});
 await panel.getByRole('button',{name:'重新导入',exact:true}).click();await expect(panel).toContainText('模拟浏览器启动失败');
 const sessions=await(await page.request.get('/api/browser-imports')).json();const failed=sessions.at(-1);
 await page.route(`**/api/browser-imports/${failed.id}`,async route=>{if(route.request().method()==='GET')await route.fulfill({json:{...failed,data:{...failed.data,status:'expired'}}});else await route.continue();});
 await panel.getByRole('button',{name:/^(重新导入|打开浏览器导入)$/}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).__importCalls.filter((c:any)=>c.command==='open-school-import').length)).toBe(1);
 expect(await page.evaluate(()=>(window as any).__importCalls.find((c:any)=>c.command==='open-school-import').payload.importId)).not.toBe(failed.id);
});
