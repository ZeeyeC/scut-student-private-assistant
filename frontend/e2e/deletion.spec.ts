import { test, expect, type Page } from '@playwright/test';

async function write(page: Page, method: string, url: string, data: unknown) {
  const csrf = (await (await page.request.get('/api/csrf')).json()).csrf_token;
  const response = await page.request.fetch('/api' + url, {
    method, data,
    headers: { Origin: 'http://127.0.0.1:5173', 'X-CSRF-Token': csrf, 'Idempotency-Key': crypto.randomUUID() },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

test('delete pending and empty plan drafts, then remove a todo and its calendar blocks after confirmation', async ({page}) => {
  await page.setViewportSize({width: 390, height: 950});
  await page.goto('/');
  await page.getByRole('button', {name:'待办 / 作业', exact:true}).click();
  await page.getByLabel('作业标题').fill('丢弃的草稿');
  await page.getByRole('button', {name:'生成校对草稿', exact:true}).click();
  await page.getByRole('button', {name:'删除草稿', exact:true}).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('丢弃的草稿', {exact:false})).toBeVisible();
  await dialog.getByRole('button', {name:'取消', exact:true}).click();
  await expect(page.getByRole('button', {name:'删除草稿', exact:true})).toBeVisible();
  await page.getByRole('button', {name:'删除草稿', exact:true}).click();
  await dialog.getByRole('button', {name:'确认删除', exact:true}).click();
  await expect(page.getByRole('button', {name:'删除草稿', exact:true})).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', {name:'待办 / 作业', exact:true}).click();
  await expect(page.getByRole('button', {name:'删除草稿', exact:true})).toHaveCount(0);

  await page.getByLabel('作业标题').fill('删除测试阅读待办');
  await page.getByRole('button', {name:'生成校对草稿', exact:true}).click();
  await page.getByRole('button', {name:'校对完成，准备保存'}).click();
  await page.getByRole('button', {name:'确认保存', exact:true}).click();
  let card = page.locator('article').filter({has:page.getByRole('heading', {name:'删除测试阅读待办', exact:true})});
  await card.getByLabel('预计耗时（分钟）').fill('30');
  await card.getByRole('button', {name:'生成排程步骤草稿'}).click();
  await card.getByRole('button', {name:'校对完成，准备保存'}).click();
  await card.getByRole('button', {name:'确认保存', exact:true}).click();
  await page.getByRole('button', {name:'今日', exact:true}).click();
  await page.getByRole('button', {name:'规划未来 7 天'}).click();
  const plan = page.locator('section').filter({has:page.getByRole('heading', {name:'未来 7 天计划'})});
  await plan.getByRole('button', {name:'校对完成，准备保存'}).click();
  await plan.getByRole('button', {name:'确认保存', exact:true}).click();
  await page.getByRole('button', {name:'课表', exact:true}).click();
  await expect(page.locator('.fc').getByText('删除测试阅读待办 · 删除测试阅读待办', {exact:true})).toBeVisible();
  card = page.locator('article').filter({has:page.getByRole('heading', {name:'删除测试阅读待办', exact:true})});
  await card.getByRole('button', {name:'删除待办', exact:true}).click();
  await expect(dialog.getByText('包含锁定和已完成的记录', {exact:false})).toBeVisible();
  await dialog.getByRole('button', {name:'取消', exact:true}).click();
  await expect(card).toBeVisible();
  await card.getByRole('button', {name:'删除待办', exact:true}).click();
  await dialog.screenshot({path:'/private/tmp/campus-delete-confirm-mobile.png'});
  await dialog.getByRole('button', {name:'确认删除', exact:true}).click();
  await expect(card).toHaveCount(0);
  await expect(page.locator('.fc').getByText('删除测试阅读待办 · 删除测试阅读待办', {exact:true})).toHaveCount(0);
  await page.getByRole('button', {name:'今日', exact:true}).click();
  await expect(page.getByRole('heading', {name:'删除测试阅读待办', exact:true})).toHaveCount(0);
  await page.getByRole('button', {name:'规划未来 7 天'}).click();
  await expect(plan.getByText('没有可保存的安排，补齐信息后重新生成。')).toBeVisible();
  await plan.getByRole('button', {name:'删除草稿', exact:true}).click();
  await dialog.getByRole('button', {name:'确认删除', exact:true}).click();
  await expect(plan).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', {name:'未来 7 天计划'})).toHaveCount(0);
  await page.getByRole('button', {name:'待办 / 作业', exact:true}).click();
  await expect(page.getByRole('heading', {name:'删除测试阅读待办', exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
});

test('stale delete cannot remove another version; refresh then explicitly confirm again', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button', {name:'待办 / 作业', exact:true}).click();
  const draft = await write(page, 'POST', '/drafts/assignment', {items:[{title:'旧版本草稿'}]});
  await page.reload();
  await page.getByRole('button', {name:'待办 / 作业', exact:true}).click();
  await page.getByRole('button', {name:'删除草稿', exact:true}).click();
  await write(page, 'PUT', '/drafts/' + draft.id, {revision:draft.revision, payload:{...draft.data.payload, items:[{...draft.data.payload.items[0], title:'另一端修改后的草稿'}]}});
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', {name:'确认删除', exact:true}).click();
  await expect(dialog.getByRole('alert')).toContainText('数据已在另一端更新');
  expect((await (await page.request.get('/api/drafts')).json()).some((d:{id:string})=>d.id===draft.id)).toBe(true);
  await dialog.getByRole('button', {name:'刷新内容', exact:true}).click();
  await page.getByRole('button', {name:'删除草稿', exact:true}).click();
  await expect(dialog.getByText('另一端修改后的草稿', {exact:false})).toBeVisible();
  await dialog.getByRole('button', {name:'确认删除', exact:true}).click();
  await expect(page.getByRole('button', {name:'删除草稿', exact:true})).toHaveCount(0);
});
