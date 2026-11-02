import {test,expect,type Page} from '@playwright/test';

async function enterWorkspace(page:Page){
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`ui-refinement-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'主导航'})).toBeVisible();
}
async function writeResource(page:Page,path:string,body:unknown){
  return page.evaluate(async({path,body})=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
    if(!r.ok)throw Error(await r.text());return r.json();
  },{path,body});
}
test('sidebar stays left while long real task content scrolls and widths change',async({page})=>{
  await page.setViewportSize({width:1280,height:782});await enterWorkspace(page);
  const draft=await writeResource(page,'/drafts/assignment',{items:Array.from({length:24},(_,i)=>({title:`滚动验证任务 ${i+1}`}))});
  await writeResource(page,`/drafts/${draft.id}/confirm`,{revision:draft.revision});
  await page.getByRole('button',{name:'任务',exact:true}).click();
  await expect(page.locator('.task-list-row')).toHaveCount(24);
  for(const width of [1280,1024,960,768,560,390,320,1280]){
    await page.setViewportSize({width,height:782});
    const sidebar=page.locator('.workspace-sidebar'),content=page.locator('#workspace-content');
    const before=await sidebar.boundingBox();
    expect(before?.x).toBe(0);expect(before?.width).toBe(width>=960?168:width>=640?144:56);
    const settingsBefore=await sidebar.getByRole('button',{name:'设置',exact:true}).boundingBox();
    await content.evaluate(el=>{el.scrollTop=el.scrollHeight;});
    expect(await content.evaluate(el=>el.scrollTop)).toBeGreaterThan(50);
    const after=await sidebar.boundingBox(),settingsAfter=await sidebar.getByRole('button',{name:'设置',exact:true}).boundingBox();
    expect(after?.y).toBeCloseTo(before!.y,1);expect(after?.height).toBeCloseTo(before!.height,1);
    expect(settingsAfter?.y).toBeCloseTo(settingsBefore!.y,1);
    expect(await page.evaluate(()=>document.scrollingElement?.scrollTop)).toBe(0);
    expect(await content.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await expect(page.getByRole('button',{name:/滚动验证任务 24/})).toBeVisible();
    await content.evaluate(el=>{el.scrollTop=0;});
  }
});

test('today add-task opens the retained review form',async({page})=>{
  await enterWorkspace(page);
  await page.getByRole('button',{name:'添加任务',exact:true}).click();
  const panel=page.getByRole('dialog',{name:'新建任务',exact:true});
  await expect(panel).toBeVisible();
  await panel.getByLabel('作业标题').fill('从今日创建的合成任务');
  expect(await(await page.request.get('/api/tasks')).json()).toEqual([]);
});

test('completion is single flight and does not fabricate execution records',async({page})=>{
  await enterWorkspace(page);
  const draft=await writeResource(page,'/drafts/assignment',{items:[{title:'整项完成合成任务'}]});
  const saved=await writeResource(page,`/drafts/${draft.id}/confirm`,{revision:draft.revision});
  await page.getByRole('button',{name:'任务',exact:true}).click();
  const checkbox=page.getByRole('checkbox',{name:'完成整项完成合成任务',exact:true});
  let writes=0;
  page.on('request',request=>{if(request.method()==='PATCH'&&request.url().endsWith('/tasks/'+saved.saved_ids[0]))writes++;});
  await checkbox.evaluate(el=>{(el as HTMLElement).click();(el as HTMLElement).click();});
  await expect.poll(async()=>(await(await page.request.get('/api/tasks/'+saved.saved_ids[0])).json()).data.status).toBe('completed');
  expect(writes).toBe(1);
  expect(await(await page.request.get('/api/tasks/'+saved.saved_ids[0]+'/executions')).json()).toEqual([]);
});
