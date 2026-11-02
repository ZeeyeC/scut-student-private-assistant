import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

async function enter(page:Page) {
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`workspace-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('navigation',{name:'主导航'})).toBeVisible();
}
test('shared navigation keeps legacy goals, reminders and compact controls reachable',async({page})=>{
  await enter(page);
  await expect(page.getByRole('navigation',{name:'主导航'}).getByRole('button')).toHaveText(['助手','今日','日程','任务','课程资料']);
  await page.addScriptTag({content:readFileSync(new URL('../../campus-pet/Resources/Bridge.js',import.meta.url),'utf8')});
  expect(await page.evaluate(()=>(window as any).__campusPet.navigate('目标与复盘'))).toBe(true);
  await expect(page.getByRole('region',{name:'长期目标',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'复盘',exact:true}).click();
  await expect(page.getByRole('region',{name:'每周复盘',exact:true})).toBeVisible();
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('campus-calendar-saved',{detail:'2026-10-30T10:00:00+08:00'})));
  await expect(page.getByRole('button',{name:'日程',exact:true})).toHaveAttribute('aria-current','page');
  for(const width of [390,320]) {
    await page.setViewportSize({width,height:844});
    await page.getByRole('button',{name:'任务',exact:true}).click();
    await expect(page.getByRole('button',{name:'设置',exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
});


test('task creation keeps its unsaved input and requires review before storing a task',async({page})=>{
  await enter(page);
  await page.getByRole('button',{name:'任务',exact:true}).click();
  await expect(page.locator('.fc')).toHaveCount(0);
  await page.getByRole('button',{name:'新建任务',exact:true}).click();
  const panel=page.getByRole('dialog',{name:'新建任务',exact:true});
  await panel.getByLabel('作业标题').fill('新界面合成任务');
  await panel.getByLabel('要求（一行一项）').fill('保留原有确认与真实数据写入');
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  await page.getByRole('button',{name:'新建任务',exact:true}).click();
  await expect(panel.getByLabel('作业标题')).toHaveValue('新界面合成任务');
  await panel.getByRole('button',{name:'生成校对草稿',exact:true}).click();
  await expect(panel.getByRole('heading',{name:'核对任务草稿',exact:true})).toBeVisible();
  expect(await (await page.request.get('/api/tasks')).json()).toHaveLength(0);
  await panel.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get('/api/tasks')).json()).length).toBe(1);
});

test('settings exposes five summaries and opens the original preference controls on demand',async({page})=>{
  await enter(page);
  await page.getByRole('button',{name:'设置',exact:true}).click();
  for(const label of ['课程与学期','学习偏好','提醒与桌宠','模型连接','资料与备份']) {
    await expect(page.getByRole('button',{name:label,exact:true})).toBeVisible();
  }
  await expect(page.getByLabel('第一周周一')).toBeHidden();
  await page.getByRole('button',{name:'学习偏好',exact:true}).click();
  const panel=page.getByRole('dialog',{name:'学习偏好',exact:true});
  await expect(panel.getByRole('region',{name:'用户偏好与精力档案'})).toContainText('未知（未设置）');
});

test('native navigation during review cannot leave the workspace permanently inert',async({page})=>{
  await enter(page);
  await page.getByRole('button',{name:'日程',exact:true}).click();
  await page.getByRole('button',{name:'安排学习',exact:true}).click();
  await page.evaluate(()=>window.dispatchEvent(new Event('campus-open-review')));
  await expect(page.getByRole('dialog',{name:'待确认',exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog',{name:'待确认',exact:true})).toBeHidden();
  await expect(page.getByRole('dialog',{name:'安排学习',exact:true})).toBeVisible();
  await page.evaluate(()=>window.dispatchEvent(new Event('campus-open-review')));
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('campus-navigate',{detail:'任务'})));
  await page.getByRole('button',{name:'关闭待确认',exact:true}).click();
  await expect.poll(()=>page.locator('.workspace-shell').evaluate(element=>(element as HTMLElement).inert)).toBe(false);
  await page.getByRole('button',{name:'新建任务',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'新建任务',exact:true})).toBeVisible();
});

test('bridge loaded before login keeps its initial native navigation until React is ready',async({page})=>{
  const bridge=readFileSync(new URL('../../campus-pet/Resources/Bridge.js',import.meta.url),'utf8');
  await page.addInitScript({content:`document.addEventListener('DOMContentLoaded',()=>{${bridge}\n});`});
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`early-bridge-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录',exact:true}).click();
  await expect(page.getByRole('heading',{name:'助手',exact:true})).toBeVisible();
});

test('mounted calendar switches views across main-window and compact widths without losing its date',async({page})=>{
  await page.setViewportSize({width:1120,height:820});await enter(page);
  await page.getByRole('button',{name:'日程',exact:true}).click();
  await expect(page.locator('.fc-timeGridWeek-view')).toBeVisible();
  const heading=await page.locator('.fc-toolbar-title').textContent();
  await page.evaluate(()=>(window as any).__originalCalendar=document.querySelector('.fc'));
  await page.setViewportSize({width:560,height:720});
  await expect(page.locator('.fc-listWeek-view')).toBeVisible();
  await page.setViewportSize({width:1120,height:820});
  await expect(page.locator('.fc-timeGridWeek-view')).toBeVisible();
  expect(await page.locator('.fc-toolbar-title').textContent()).toBe(heading);
  expect(await page.evaluate(()=>(window as any).__originalCalendar===document.querySelector('.fc'))).toBe(true);
});
