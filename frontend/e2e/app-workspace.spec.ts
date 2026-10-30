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
  await expect(page.getByRole('navigation',{name:'主导航'}).getByRole('button')).toHaveText(['今日','日程','任务','助手']);
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

