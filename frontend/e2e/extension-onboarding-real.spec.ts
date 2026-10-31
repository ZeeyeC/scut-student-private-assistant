import {test,expect,chromium,type Page} from '@playwright/test';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
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


test('fresh Chromium profile loads the bundled real extension and returns a synthetic school timetable',async({page})=>{
 test.setTimeout(60000);const issued=await issueInApp(page);
 const profile=await mkdtemp(join(tmpdir(),'campus-extension-user-'));
 const extension=fileURLToPath(new URL('../../extension/.output/chrome-mv3',import.meta.url));
 const context=await chromium.launchPersistentContext(profile,{channel:'chromium',executablePath:process.env.PET_EXTENSION_BROWSER,headless:true,args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
 try {
  await context.route('http://127.0.0.1:5173/**',async route=>{const headers={...route.request().headers()};if(headers.origin)headers.origin=headers.origin.replace(':5173',':5290');if(headers.referer)headers.referer=headers.referer.replace(':5173',':5290');const response=await route.fetch({url:route.request().url().replace('http://127.0.0.1:5173','http://127.0.0.1:5290'),headers});await route.fulfill({response});});
  await context.route('http://xsjw2018.jw.scut.edu.cn/**',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><meta charset="utf-8"><h1>合成学校页面</h1><select id="xnm"><option>2026-2027</option></select><select id="xqm"><option>1</option></select><button id="search_go" onclick="setTimeout(()=>document.querySelector('#kblist_table').append(document.createTextNode('已查询')),100)">查询课表</button><table id="kblist_table"><tr><td><div class="timetable_title"><h6 class="pull-left">2026-2027学年第1学期</h6></div></td></tr><tr><td id="jc_1-1-2">1-2</td><td><div class="timetable_con"><span class="title"><font color="blue">真实扩展合成数学</font></span><p><font>周数：1-8周</font><font>校区:大学城校区 上课地点：A101</font><font>教师：测试教师</font></p></div></td></tr></table>`}));
  const external=await context.newPage();
  await external.goto('http://127.0.0.1:5173'+issued.grant.bridge_path+'#grant='+issued.grant.grant_id+'.'+issued.secret);
  let worker=context.serviceWorkers()[0];if(!worker)worker=await context.waitForEvent('serviceworker');
  expect(await worker.evaluate(()=>(globalThis as any).chrome.runtime.getManifest().name)).toBe('课间 · 华工课表桥接');
  await expect.poll(async()=>{const alert=external.getByRole('alert');if(await alert.count())throw new Error(await alert.innerText());return await external.getByRole('status').innerText();},{timeout:15000}).toContain('请本人登录学校');
  await expect.poll(()=>context.pages().some(p=>p.url().includes('xsjw2018.jw.scut.edu.cn'))).toBe(true);
  const school=context.pages().find(p=>p.url().includes('xsjw2018.jw.scut.edu.cn'))!;
  await school.goto('http://xsjw2018.jw.scut.edu.cn/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151&layout=default');
  await school.getByRole('button',{name:'查询课表'}).click();
  await expect(external.getByRole('status')).toContainText('已回传',{timeout:20000});
  const session=await(await page.request.get(`/api/browser-imports/${issued.session.id}`)).json();expect(session.data.status).toBe('preview_ready');
  expect(await(await page.request.get('/api/courses')).json()).toEqual([]);
 }finally{await context.close();await rm(profile,{recursive:true,force:true});}
});
