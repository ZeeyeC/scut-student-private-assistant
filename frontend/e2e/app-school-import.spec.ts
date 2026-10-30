import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

async function issueInApp(page:Page){
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`bridge-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('navigation',{name:'主导航'})).toBeVisible();
  return await page.evaluate(async()=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    const post=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok)throw new Error(await r.text());return r.json();
    };
    const settings=await(await fetch('/api/settings')).json();
    settings.data={...settings.data,week1_monday:'2026-10-26',periods:{1:{start:'09:00',end:'10:00'},2:{start:'10:00',end:'11:00'}}};
    await post('/settings',settings,'PUT');
    const session=await post('/browser-imports',{school_id:'scut'});
    const secret='b'.repeat(64);
    const grant=await post(`/browser-imports/${session.id}/desktop-grant`,{client_token:secret});
    return {session,grant,secret};
  });
}

test('external import has no App cookie, clears its grant from the URL and returns a draft for App approval',async({page,browser})=>{
  const issued=await issueInApp(page);
  const context=await browser.newContext({baseURL:'http://127.0.0.1:5290'});
  const external=await context.newPage();
  await external.addInitScript(()=>{
    window.addEventListener('message',event=>{
      if(event.source!==window||event.data?.channel!=='campus-assistant-v1')return;
      const {action,nonce,requestId,payload}=event.data;
      const result=action==='detect'?{installed:true}:action==='stop'?null:{
        ...payload,events:['opened','waiting_timetable','extracting'].map(kind=>({kind,event_id:'fixture-'+kind})),
        capture:{semester_label:'合成学校导入',fragments:['<table><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th></tr><tr><td>合成导入数学</td><td>1</td><td>1-8</td><td>1-2</td><td>A101</td></tr></table>']},
      };
      window.postMessage({channel:'campus-assistant-reply-v1',nonce,requestId,result},location.origin);
    });
  });
  await external.goto(issued.grant.bridge_path+'#grant='+issued.grant.grant_id+'.'+issued.secret);
  await expect(external.getByRole('heading',{name:'学校课表导入',exact:true})).toBeVisible();
  await expect(external.getByRole('navigation',{name:'主导航'})).toHaveCount(0);
  await expect.poll(()=>external.evaluate(()=>location.hash)).toBe('');
  await expect(external.getByRole('status')).toContainText('已回传');
  expect((await external.request.get('/api/tasks')).status()).toBe(401);
  expect(await(await page.request.get('/api/courses')).json()).toEqual([]);
  await expect.poll(async()=> (await(await page.request.get(`/api/browser-imports/${issued.session.id}`)).json()).data.status).toBe('preview_ready');
  await page.getByRole('button',{name:/^待确认/}).click();
  const panel=page.getByRole('dialog',{name:'待确认',exact:true});
  await expect(panel).toContainText('合成导入数学');
  await panel.getByRole('button',{name:'校对完成，准备保存',exact:true}).click();
  const acknowledgment=panel.getByRole('checkbox',{name:'我已核对上述提示，仍按已确认的课程或事项保存'});
  if(await acknowledgment.count())await acknowledgment.check();
  await panel.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect.poll(async()=> (await(await page.request.get('/api/courses')).json()).length).toBe(1);
  await context.close();
});


test('missing extension stays in the import flow and App cancellation revokes retry',async({page,browser})=>{
  const issued=await issueInApp(page);
  const context=await browser.newContext({baseURL:'http://127.0.0.1:5290'});
  const external=await context.newPage();
  await external.goto(issued.grant.bridge_path+'#grant='+issued.grant.grant_id+'.'+issued.secret);
  await expect(external.getByRole('status')).toContainText('未检测到课表扩展',{timeout:10000});
  expect(context.pages()).toHaveLength(1);
  await page.locator('.import-progress').click();
  const panel=page.getByRole('dialog',{name:'学校课表',exact:true});
  await expect(panel).toContainText('未检测到扩展',{timeout:10000});
  await panel.getByRole('button',{name:'取消导入',exact:true}).click();
  await expect.poll(async()=>(await(await page.request.get(`/api/browser-imports/${issued.session.id}`)).json()).data.status).toBe('cancelled');
  await external.getByRole('button',{name:'重新检测',exact:true}).click();
  await expect(external.getByRole('alert')).toContainText('取消');
  expect(await(await page.request.get('/api/courses')).json()).toEqual([]);
  await context.close();
});

test('App browser selection uses the native bridge and a double click starts only one import',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`native-import-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('navigation',{name:'主导航'})).toBeVisible();
  await page.evaluate(()=>{
    const state={browser:'chrome',installed:true};
    (window as any).__nativeImportCalls=[];
    Object.defineProperty(window,'webkit',{configurable:true,value:{messageHandlers:{petState:{postMessage(message:any){
      if(message?.channel!=='school-import-v1')return;
      (window as any).__nativeImportCalls.push(message);
      if(message.command==='set-browser')state.browser=message.payload.browser;
      setTimeout(()=>window.dispatchEvent(new CustomEvent('campus-native-import-result',{detail:{requestId:message.requestId,ok:true,result:{...state}}})),message.command==='open-school-import'?100:0);
    }}}}});
  });
  await page.addScriptTag({content:readFileSync(new URL('../../campus-pet/Resources/Bridge.js',import.meta.url),'utf8')});
  await page.getByRole('button',{name:'日程',exact:true}).click();
  await page.getByRole('button',{name:'导入课表',exact:true}).click();
  await page.getByRole('button',{name:'学校课表',exact:true}).click();
  const panel=page.getByRole('dialog',{name:'学校课表',exact:true});
  await expect(panel.getByLabel('课表导入浏览器')).toHaveValue('chrome');
  await panel.getByLabel('课表导入浏览器').selectOption('edge');
  await expect(panel.getByLabel('课表导入浏览器')).toHaveValue('edge');
  await panel.getByRole('button',{name:'打开浏览器导入',exact:true}).dblclick();
  await expect.poll(()=>page.evaluate(()=>(window as any).__nativeImportCalls.filter((call:any)=>call.command==='open-school-import').length)).toBe(1);
  expect(await(await page.request.get('/api/browser-imports')).json()).toHaveLength(1);
  expect((await page.evaluate(()=>(window as any).__nativeImportCalls.find((call:any)=>call.command==='open-school-import'))).payload.importId).toMatch(/^[a-f0-9-]{36}$/);
});
