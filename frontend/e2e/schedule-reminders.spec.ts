import {workspace,inbox} from './workspace';
import { test, expect } from '@playwright/test';

test('calendar shortcut persists website and file choices and controls reminders', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`reminder-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
  await page.evaluate(async()=>{
    const token=(await (await fetch('/api/csrf')).json()).csrf_token;
    const start=new Date(Date.now()+240000); const end=new Date(start.getTime()+3600000);
    const response=await fetch('/api/fixed-events',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({title:'提醒验收任务',starts_at:start.toISOString(),ends_at:end.toISOString()})});
    if(!response.ok) throw new Error(await response.text());
  });
  await workspace(page,'calendar');
  await page.locator('.fc-event').filter({hasText:'提醒验收任务'}).first().click();
  await page.getByLabel('点击奶娃时打开').selectOption('website');
  await page.getByLabel('完整网站地址').fill('https://example.com/homework');
  await page.getByRole('button',{name:'保存提醒设置'}).click();
  await expect(page.getByRole('status').filter({hasText:'已保存'})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator('.fc-event').filter({hasText:'提醒验收任务'}).first().click();
  await expect(page.getByLabel('完整网站地址')).toHaveValue('https://example.com/homework');
  await page.getByLabel('点击奶娃时打开').selectOption('file');
  await page.getByLabel('文件完整路径').fill('/tmp/中文 作业.pdf');
  await page.getByRole('button',{name:'保存提醒设置'}).click();
  await expect(page.getByRole('status').filter({hasText:'已保存'})).toBeVisible();
  const due=await (await page.request.get('/api/schedule-reminders')).json();
  expect(due).toHaveLength(1); expect(due[0].target).toBe('/tmp/中文 作业.pdf');
  await page.getByLabel('开始前 5 分钟提醒',{exact:true}).uncheck();
  await page.getByRole('button',{name:'保存提醒设置'}).click();
  await expect(page.getByRole('status').filter({hasText:'已保存'})).toBeVisible();
  expect(await (await page.request.get('/api/schedule-reminders')).json()).toHaveLength(0);
});
