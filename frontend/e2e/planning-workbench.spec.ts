import {workspace,inbox} from './workspace';
import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';
async function enter(page:Page) {
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`workbench-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');const bootstrap=page.waitForResponse(r=>r.url().endsWith('/api/after-class/open')&&r.request().method()==='POST');await page.getByRole('button',{name:'注册并登录'}).click();await (await bootstrap).finished();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
}
async function seed(page:Page) {
  await page.evaluate(async()=>{
    const csrf=(await (await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok)throw new Error(await r.text());return r.json();
    };
    const settings=await (await fetch('/api/settings')).json();settings.data={...settings.data,study_windows:[{start:'19:00',end:'22:00'}],buffer_minutes:0,daily_limit_minutes:180};await write('/settings',settings,'PUT');
    const a=await write('/drafts/assignment',{items:[{title:'方案测试练习',due_at:'2026-10-15T22:00:00+08:00'}]});
    const saved=await write(`/drafts/${a.id}/confirm`,{revision:a.revision});const task=await (await fetch('/api/tasks/'+saved.saved_ids[0])).json();
    const step=await write(`/tasks/${task.id}/step-drafts`,{task_revision:task.revision,steps:[{key:'a',title:'步骤',description:'合成验收',estimated_minutes:60,dependency_keys:[],acceptance_criteria:['完成']}]});await write(`/drafts/${step.id}/confirm`,{revision:step.revision});
  });
}
test('soft preference is confirmed then compared and selected through the existing plan review',async({page})=>{
  await enter(page);await seed(page);await workspace(page,'planning');
  await page.getByRole('button',{name:'添加禁排时段'}).click();
  await page.getByLabel('约束类型').selectOption('soft');await page.getByLabel('禁排名称',{exact:true}).fill('明确晚间偏好');
  await page.getByLabel('禁排开始',{exact:true}).fill('2026-10-14T21:00');await page.getByLabel('禁排结束',{exact:true}).fill('2026-10-14T22:00');
  await page.getByRole('button',{name:'生成禁排草稿'}).click();
  const constraint=page.getByRole('region',{name:'禁排草稿',exact:true});await expect(constraint).toContainText('软偏好');
  await constraint.getByRole('button',{name:'确认保存',exact:true}).click();await expect(constraint).toHaveCount(0);
  const panel=page.getByRole('region',{name:'规划方案与日常候选',exact:true});
  await expect(panel.getByRole('article',{name:'更早开始',exact:true})).toContainText('偏好内 0 分钟');
  await expect(panel.getByRole('article',{name:'遵循软偏好',exact:true})).toContainText('偏好内 60 分钟');
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual([]);
  await panel.getByRole('button',{name:'选择遵循软偏好'}).click();
  const plan=page.getByRole('region',{name:'计划草稿',exact:true});await expect(plan).toContainText('优先使用已确认软偏好窗口');
  await plan.getByRole('button',{name:'确认保存',exact:true}).click();await expect(plan).toHaveCount(0);
  const blocks=await (await page.request.get('/api/plan-blocks')).json();expect(new Date(blocks[0].data.starts_at).getUTCHours()).toBe(13);
});
test('mobile explicit routine preview supports durable rejection and reviewed saving without guessing',async({page})=>{
  await page.setViewportSize({width:390,height:844});await enter(page);await seed(page);await workspace(page,'planning');
  const panel=page.getByRole('region',{name:'规划方案与日常候选',exact:true});
  await panel.getByLabel('上述规则由我明确指定，仅生成待确认候选').check();await panel.getByRole('button',{name:'预览日常候选'}).click();await expect(panel).toContainText('未提供明确作息或准备规则');
  await panel.getByLabel('作息名称（可留空）').fill('明确休息');await panel.getByLabel('作息开始',{exact:true}).fill('19:00');await panel.getByLabel('作息结束',{exact:true}).fill('19:30');await panel.getByRole('button',{name:'预览日常候选'}).click();
  const candidate=panel.getByRole('article').filter({has:page.getByRole('heading',{name:'明确休息',exact:true})}).first();
  await candidate.getByRole('button',{name:'忽略此候选'}).click();await expect(candidate).toContainText('已忽略');
  await panel.getByRole('button',{name:'预览日常候选'}).click();await expect(candidate).toContainText('已忽略');
  const next=panel.getByRole('article').filter({has:page.getByRole('heading',{name:'明确休息',exact:true})}).nth(1);
  await next.getByRole('button',{name:'校对此候选'}).click();const review=page.locator('section').filter({has:page.getByRole('heading',{name:'核对日程事项',exact:true})}).last();
  expect(await (await page.request.get('/api/fixed-events')).json()).toEqual([]);
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();await review.getByRole('button',{name:'确认保存',exact:true}).click();await expect(page.getByRole('heading',{name:'核对日程事项',exact:true})).toHaveCount(0);
  expect(await (await page.request.get('/api/fixed-events')).json()).toHaveLength(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await panel.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.5.1/e2e/planning-workbench.png',import.meta.url))});
});
