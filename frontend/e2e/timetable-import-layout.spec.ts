import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';
async function enter(page:Page){
 await page.addInitScript(()=>{
  const state={browser:'edge',installed:true};(window as any).__importCalls=[];
  (window as any).__campusNative={request:async(command:string,payload:any)=>{(window as any).__importCalls.push({command,payload});if(command==='set-browser')state.browser=payload.browser;return {...state};}};
 });
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`import-layout-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');await page.getByRole('button',{name:'注册并登录',exact:true}).click();
 await page.getByRole('button',{name:'日程',exact:true}).click();await page.getByRole('button',{name:'导入课表',exact:true}).click();
}
test('browser is the primary default and opening the panel has no launch or write side effect',async({page})=>{
 await enter(page);const panel=page.getByRole('dialog',{name:'导入课表',exact:true});
 await expect(panel.getByRole('heading',{name:'从学校导入',exact:true})).toBeVisible();
 await expect(panel.getByLabel('课表导入浏览器')).toHaveValue('edge');
 await expect(panel.getByRole('button',{name:'图片 / PDF',exact:true})).toHaveAttribute('aria-expanded','false');
 await expect(panel.getByRole('button',{name:'文字导入',exact:true})).toHaveAttribute('aria-expanded','false');
 expect(await page.evaluate(()=>(window as any).__importCalls.filter((c:any)=>c.command==='open-school-import').length)).toBe(0);
 expect(await(await page.request.get('/api/browser-imports')).json()).toHaveLength(0);
 await panel.getByRole('button',{name:'打开浏览器导入',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).__importCalls.filter((c:any)=>c.command==='open-school-import').length)).toBe(1);
});
test('secondary methods retain their input and never launch or recognize by expanding',async({page})=>{
 await enter(page);const panel=page.getByRole('dialog',{name:'导入课表',exact:true});let writes=0;
 page.on('request',r=>{if(r.method()==='POST'&&/timetable-(jobs|assets)/.test(r.url()))writes++;});
 await panel.getByRole('button',{name:'图片 / PDF',exact:true}).click();
 await panel.getByLabel('课表图片或 PDF', {exact:true}).setInputFiles(fileURLToPath(new URL('fixtures/synthetic-test.png',import.meta.url)));
 await panel.getByRole('button',{name:'文字导入',exact:true}).click();
 await panel.getByLabel('给助手的消息').fill('保留这段合成课表输入');
 await page.keyboard.press('Escape');await page.getByRole('button',{name:'导入课表',exact:true}).click();
 await panel.getByRole('button',{name:'文字导入',exact:true}).click();
 await expect(panel.getByLabel('给助手的消息')).toHaveValue('保留这段合成课表输入');
 await panel.getByRole('button',{name:'图片 / PDF',exact:true}).click();
 expect(await panel.getByLabel('课表图片或 PDF',{exact:true}).inputValue()).toContain('synthetic-test.png');
 expect(writes).toBe(0);
 expect(await page.evaluate(()=>(window as any).__importCalls.filter((c:any)=>c.command==='open-school-import').length)).toBe(0);
});
