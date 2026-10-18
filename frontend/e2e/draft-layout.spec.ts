import { test, expect } from '@playwright/test';

test('drafts use available width; chat has compact toolbar and full composer at every size', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button', {name:'待办与日程',exact:true}).click();
  for (const title of ['布局草稿一','布局草稿二']) {
    await page.getByLabel('作业标题').fill(title);
    await page.getByRole('button',{name:'生成校对草稿',exact:true}).click();
    await expect(page.getByRole('heading',{name:'核对任务草稿'})).toHaveCount(title.endsWith('一') ? 1 : 2);
  }
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({width,height:950});
    const review = page.locator('section').filter({has:page.getByRole('heading',{name:'核对任务草稿'})}).first();
    const area = await review.boundingBox(), fields = await review.locator('fieldset').boundingBox();
    expect(fields!.width / area!.width).toBeGreaterThan(.72);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+2)).toBe(true);
  }
  await page.getByRole('button',{name:'助手',exact:true}).click();
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({width,height:950});
    const input=await page.getByLabel('给助手的消息').boundingBox();
    const composer=await page.locator('.composer').boundingBox();
    const chat=await page.locator('.chat').boundingBox();
    const head=await page.locator('.chat-toolbar').boundingBox();
    expect(head!.height).toBeLessThan(100);
    expect(chat!.height).toBeGreaterThan(480);
    expect(composer!.width/chat!.width).toBeGreaterThan(.85);
    expect(input!.width).toBeGreaterThan(composer!.width - 120);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+2)).toBe(true);
  }
  for (let i=0;i<2;i++) {
    const review=page.locator('section').filter({has:page.getByRole('heading',{name:'核对任务草稿'})}).first();
    await review.getByRole('button',{name:'校对完成，准备保存'}).click();
    await review.getByRole('button',{name:'确认保存',exact:true}).click();
    await expect(page.getByRole('heading',{name:'核对任务草稿'})).toHaveCount(1-i);
  }
  expect(await (await page.request.get('/api/tasks')).json()).toHaveLength(2);
});
