import {test, expect} from '@playwright/test';

test('academic dates appear without a picker, conversation edits the same draft and both save', async ({page})=>{
  await page.setViewportSize({width:1440,height:950});
  await page.goto('/');
  await page.getByRole('button',{name:'助手',exact:true}).click();
  const csrf = (await (await page.request.get('/api/csrf')).json()).csrf_token;
  const settings = await (await page.request.get('/api/settings')).json();
  settings.data.week1_monday = '2026-08-31';
  expect((await page.request.put('/api/settings',{data:settings,headers:{'X-CSRF-Token':csrf,Origin:'http://127.0.0.1:5173','Idempotency-Key':'semester'}})).ok()).toBe(true);
  const send = async(text:string)=>{
    await page.getByLabel('给助手的消息').fill(text);
    await page.getByRole('button',{name:'发送',exact:true}).click();
  };
  await send('第14周之前我要完成C++大作业，11周之前要完成agent大作业，帮我添加到待办事项');
  const reviews=page.locator('.assignment-review');
  await expect(reviews).toHaveCount(2);
  const byTitle=(title:string)=>reviews.filter({has:page.locator(`input[value="${title}"]`)});
  await expect(byTitle('C++大作业').getByLabel('确认后的截止时间')).toHaveValue('2026-11-30T00:00');
  await expect(byTitle('agent大作业').getByLabel('确认后的截止时间')).toHaveValue('2026-11-09T00:00');
  await expect(byTitle('C++大作业').getByText(/按首周周一/)).toBeVisible();
  expect(await (await page.request.get('/api/tasks')).json()).toHaveLength(0);
  const original = (await (await page.request.get('/api/drafts')).json()).find((d:any)=>d.data.payload.items[0].title==='C++大作业');
  await page.screenshot({path:'/private/tmp/campus-academic-desktop.png',fullPage:true});
  await send('把 C++ 大作业草稿的截止改成明天晚上8点');
  await expect(byTitle('C++大作业').getByLabel('确认后的截止时间')).toHaveValue(/T20:00$/);
  const updated = await (await page.request.get('/api/drafts')).json();
  expect(updated).toHaveLength(2);
  expect(updated.find((d:any)=>d.id===original.id).revision).toBe(original.revision+1);
  expect(await (await page.request.get('/api/tasks')).json()).toHaveLength(0);
  await page.setViewportSize({width:390,height:950});
  await page.reload();
  await page.getByRole('button',{name:'助手',exact:true}).click();
  await expect(byTitle('C++大作业').getByLabel('确认后的截止时间')).toHaveValue(/T20:00$/);
  await page.screenshot({path:'/private/tmp/campus-academic-mobile.png',fullPage:true});
  for (const title of ['C++大作业','agent大作业']) {
    const review=byTitle(title);
    await review.getByRole('button',{name:'校对完成，准备保存'}).click();
    await review.getByRole('button',{name:'确认保存',exact:true}).click();
    await expect(review).toHaveCount(0);
  }
  const tasks=await (await page.request.get('/api/tasks')).json();
  expect(tasks).toHaveLength(2);
  expect(tasks.find((t:any)=>t.data.title==='C++大作业').data.due_at).toContain('T20:00');
  expect(tasks.find((t:any)=>t.data.title==='agent大作业').data.due_at).toBe('2026-11-09T00:00:00+08:00');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2)).toBe(true);
});
