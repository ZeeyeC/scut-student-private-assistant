import {workspace,inbox} from './workspace';
import { test, expect, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

async function enter(page: Page) {
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button', {name:'创建账号', exact:true}).click();
  await page.getByLabel('邮箱').fill(`capacity-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  const bootstrap = page.waitForResponse(r => r.url().endsWith('/api/after-class/open') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'注册并登录'}).click();
  await (await bootstrap).finished();
  await expect(page.getByRole('heading', {name:'今日',exact:true})).toBeVisible();
}

async function seed(page: Page) {
  await page.evaluate(async () => {
    const csrf = (await (await fetch('/api/csrf')).json()).csrf_token;
    const write = async (path:string, body:unknown, method='POST') => {
      const r = await fetch('/api' + path, {method, headers:{'Content-Type':'application/json', 'X-CSRF-Token':csrf, 'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify(body)});
      if (!r.ok) throw new Error(await r.text()); return r.json();
    };
    const settings = await (await fetch('/api/settings')).json();
    settings.data = {...settings.data, week1_monday:'2026-10-12', buffer_minutes:0, study_windows:[{start:'19:00', end:'22:00'}], daily_limit_minutes:180, periods:{'1':{start:'19:00',end:'20:00'}}};
    await write('/settings', settings, 'PUT');
    const course = await write('/drafts/timetable', {semester_label:'合成容量验收', courses:[{source_key:'fixed',name:'晚间课程',weekday:3,weeks:[1],periods:[1]}]});
    await write(`/drafts/${course.id}/confirm`, {revision:course.revision});
    const constraint = await write('/drafts/scheduling-constraint', {constraint:{title:'晚间休息',timezone:'Asia/Shanghai',starts_at:'2026-10-14T20:00:00+08:00',ends_at:'2026-10-14T20:30:00+08:00'}});
    await write(`/drafts/${constraint.id}/confirm`, {revision:constraint.revision});
    const assignment = await write('/drafts/assignment', {items:[{title:'容量练习',due_at:'2026-10-17T22:00:00+08:00'}, {title:'尚未估时的阅读',due_at:'2026-10-17T22:00:00+08:00'}]});
    const saved = await write(`/drafts/${assignment.id}/confirm`, {revision:assignment.revision});
    const task = await (await fetch(`/api/tasks/${saved.saved_ids[0]}`)).json();
    const step = await write(`/tasks/${task.id}/step-drafts`, {task_revision:task.revision,steps:[{key:'a',title:'练习步骤',description:'合成验收',estimated_minutes:180,dependency_keys:[],acceptance_criteria:['完成']}]});
    await write(`/drafts/${step.id}/confirm`, {revision:step.revision});
  });
}

test('capacity is read-only, distinguishes shortage and unknown work, matches the confirmed planner', async ({page}) => {
  await enter(page); await seed(page);
  let before = (await (await page.request.get('/api/data-export')).json()).resources;
  await page.request.get('/api/planning-capacity?scope=today');
  expect((await (await page.request.get('/api/data-export')).json()).resources).toEqual(before);
  const consumed=page.waitForResponse(r=>r.url().endsWith('/api/replanning/changes')&&r.request().method()==='POST');
  await workspace(page,'planning');
  await (await consumed).finished();
  const afterNavigation=(await (await page.request.get('/api/data-export')).json()).resources;
  // Mounting the new active change consumer may write its notice/event cursor;
  // every business fact must stay unchanged, and capacity reads stay fully pure.
  const facts=(rows:any[])=>rows.filter(r=>!['planning_event','replan_notice'].includes(r.kind));
  expect(facts(afterNavigation)).toEqual(facts(before));
  before=afterNavigation;
  const panel = page.getByRole('region', {name:'时间容量检查',exact:true});
  await expect(panel).toContainText('容量上限 90 分钟');
  await expect(panel).toContainText('待分配 180 分钟 · 本范围可排 90 分钟 · 仍未排 90 分钟');
  await expect(panel).toContainText('还有 1 项待办缺少步骤耗时');
  await expect(panel).toContainText('尚未估时的阅读');
  await panel.getByText('查看可用空档', {exact:true}).click();
  await expect(panel).toContainText('20:30–22:00');
  expect((await (await page.request.get('/api/data-export')).json()).resources).toEqual(before);
  await panel.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.9/e2e/planning-capacity.png',import.meta.url))});
  await panel.getByRole('button', {name:'未来7天容量',exact:true}).click();
  await expect(panel).toContainText('本范围可排 180 分钟 · 仍未排 0 分钟');
  await expect(panel.getByRole('article')).toHaveCount(7);
  expect((await (await page.request.get('/api/data-export')).json()).resources).toEqual(before);
  await panel.getByRole('button', {name:'今天剩余时间',exact:true}).click();
  await expect(panel).toContainText('本范围可排 90 分钟');
  await page.getByRole('region', {name:'智能安排',exact:true}).getByRole('button', {name:'一键生成当日日程',exact:true}).click();
  const review = page.getByRole('region', {name:'计划草稿',exact:true});
  await expect(review.getByRole('button', {name:'确认保存',exact:true})).toBeVisible();
  const drafts = await (await page.request.get('/api/drafts')).json();
  const p = drafts.find((d:any) => d.data.draft_kind === 'plan' && d.data.status === 'pending').data.payload;
  expect(p.capacity.proposed_minutes).toBe(90);
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual([]);

  await review.getByRole('button', {name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
  await panel.getByRole('button', {name:'刷新容量',exact:true}).click();
  await expect(panel).toContainText(`保留 ${p.blocks.length} 项`);
  await page.reload();
  await workspace(page,'planning');
  await expect(panel).toContainText('本范围可排 90 分钟');
});

test('mobile capacity reports an empty window and recovers from a failed read without saving work', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await enter(page);
  await page.evaluate(async () => {
    const csrf = (await (await fetch('/api/csrf')).json()).csrf_token;
    const settings = await (await fetch('/api/settings')).json();
    settings.data.study_windows = [];
    const r = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(settings)});
    if (!r.ok) throw new Error(await r.text());
  });
  await page.route('**/api/planning-capacity?*', route => route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'合成离线'})}));
  await workspace(page,'planning');
  const panel = page.getByRole('region', {name:'时间容量检查',exact:true});
  await expect(panel.getByRole('alert')).toContainText('容量检查失败');
  await page.unroute('**/api/planning-capacity?*');
  await panel.getByRole('button', {name:'刷新容量'}).click();
  await expect(panel).toContainText('容量上限 0 分钟');
  await panel.getByText('查看可用空档', {exact:true}).click();
  await expect(panel).toContainText('没有可用空档');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(await (await page.request.get('/api/drafts')).json()).toEqual([]);
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual([]);
});
