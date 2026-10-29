import { test, expect, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

async function enter(page: Page) {
  await page.clock.setFixedTime(new Date("2026-10-14T10:30:00Z"));
  await page.goto("/");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("邮箱").fill(`constraint-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: "今天，专注几件事。" })).toBeVisible();
  await page.getByRole("button", { name: "待办与日程", exact: true }).click();
}

async function prepare(page: Page, title = "不可安排") {
  await page.getByRole("button", { name: "添加禁排时段" }).click();
  await page.getByLabel("禁排名称", { exact: true }).fill(title);
  await page.getByLabel("禁排开始", { exact: true }).fill("2026-10-14T19:00");
  await page.getByLabel("禁排结束", { exact: true }).fill("2026-10-14T21:00");
  await page.getByRole("button", { name: "生成禁排草稿" }).click();
  await expect(page.getByRole("region", { name: "禁排草稿", exact: true })).toBeVisible();
}

async function save(page: Page) {
  const review = page.getByRole("region", { name: "禁排草稿", exact: true });
  await review.getByRole("button", { name: "校对完成，准备保存" }).click();
  await review.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(review).toHaveCount(0);
}

test("one-off protection is reviewed, persists, changes plans and does not become a course or reminder", async ({ page }) => {
  await enter(page);
  await page.evaluate(async () => {
    const token = (await (await fetch("/api/csrf")).json()).csrf_token;
    const write = async (path: string, body: unknown) => {
      const r = await fetch("/api" + path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token, "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    };
    const d = await write("/drafts/assignment", { items: [{ title: "禁排验收练习", due_at: "2026-10-14T21:00:00+08:00" }] });
    const result = await write(`/drafts/${d.id}/confirm`, { revision: d.revision });
    const tid = result.saved_ids[0];
    const t = await (await fetch(`/api/tasks/${tid}`)).json();
    const step = await write(`/tasks/${tid}/step-drafts`, { task_revision: t.revision, steps: [{ key: "a", title: "禁排验收练习", description: "合成验收", estimated_minutes: 60, dependency_keys: [], acceptance_criteria: ["完成"] }] });
    await write(`/drafts/${step.id}/confirm`, { revision: step.revision });
  });
  await prepare(page);
  expect(await (await page.request.get("/api/scheduling-constraints")).json()).toEqual([]);
  await page.reload();
  await page.getByRole("button", { name: "待办与日程", exact: true }).click();
  await expect(page.getByRole("region", { name: "禁排草稿", exact: true })).toContainText("尚未生效");
  await save(page);
  await expect(page.getByRole("heading", { name: "不可安排 · 已启用", exact: true })).toBeVisible();
  await expect(page.locator(".fc-event").filter({ hasText: "不可安排" })).toHaveCount(1);
  await page.locator(".fc-event").filter({ hasText: "不可安排" }).click();
  const detail = page.getByRole("region", { name: "日程详情", exact: true });
  await expect(detail).toContainText("不触发提醒");
  await expect(detail.getByRole("region", { name: "提醒与快捷打开" })).toHaveCount(0);
  await page.getByRole("button", { name: "关闭详情" }).click();
  await page.getByRole("button", { name: "智能安排未来 7 天" }).click();
  const plan = page.getByRole("region", { name: "智能安排", exact: true });
  await expect(plan.getByRole("heading", { name: "仍未安排" })).toBeVisible();
  await expect(plan).toContainText("禁排验收练习");
  await expect(plan).toContainText("60 分钟");
  expect(await (await page.request.get("/api/plan-blocks")).json()).toEqual([]);
  await page.getByRole("button", { name: "停用禁排" }).click();
  await expect(page.getByRole("heading", { name: "不可安排 · 已停用", exact: true })).toBeVisible();
  await expect(page.locator(".fc-event").filter({ hasText: "不可安排" })).toHaveCount(0);
  await page.getByRole("button", { name: "智能安排未来 7 天" }).click();
  await expect(plan).not.toContainText("仍未安排");
  await expect(plan).toContainText("本次分配 60 分钟");
  await plan.getByRole("button", { name: "校对完成，准备保存" }).click();
  await plan.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get("/api/plan-blocks")).json()).length).toBe(1);
  const exported = await (await page.request.get("/api/data-export")).json();
  expect(exported.resources.filter((r: any) => r.kind === "plan_snapshot")).toHaveLength(1);
  await page.getByRole("button", { name: "启用禁排" }).click();
  await expect(page.getByRole("heading", { name: "不可安排 · 已启用", exact: true })).toBeVisible();
  expect((await (await page.request.get("/api/plan-blocks")).json()).length).toBe(1);
  await page.getByRole("button", { name: "课表", exact: true }).click();
  await expect(page.locator(".fc-event").filter({ hasText: "不可安排" })).toHaveCount(0);
});

test("lost draft response replays once; edit changes the existing constraint after review", async ({ page }) => {
  await enter(page);
  let lose = true;
  await page.route("**/api/drafts/scheduling-constraint", async route => {
    if (!lose) { await route.continue(); return; }
    lose = false;
    const response = await route.fetch();
    expect(response.ok()).toBe(true);
    await route.abort();
  });
  await page.getByRole("button", { name: "添加禁排时段" }).click();
  await page.getByLabel("禁排开始", { exact: true }).fill("2026-10-14T19:00");
  await page.getByLabel("禁排结束", { exact: true }).fill("2026-10-14T21:00");
  await page.getByRole("button", { name: "生成禁排草稿" }).click();
  await expect(page.getByRole("form", { name: "编辑禁排时段" }).getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "生成禁排草稿" }).click();
  const drafts = await (await page.request.get("/api/drafts")).json();
  expect(drafts.filter((d: any) => d.data.draft_kind === "scheduling_constraint")).toHaveLength(1);
  await save(page);
  await page.getByRole("button", { name: "修改时段", exact: true }).click();
  await page.getByLabel("禁排名称", { exact: true }).fill("午休保护");
  await page.getByRole("button", { name: "生成禁排草稿" }).click();
  await expect(page.getByRole("heading", { name: "不可安排 · 已启用", exact: true })).toBeVisible();
  await save(page);
  await expect(page.getByRole("heading", { name: "午休保护 · 已启用", exact: true })).toBeVisible();
  expect((await (await page.request.get("/api/scheduling-constraints")).json()).length).toBe(1);
  await page.screenshot({ path: "/private/tmp/planning-foundation-constraints.png", fullPage: true });
});

test('weekly protection previews dates, survives reload and guides today and seven-day planning',async({page})=>{
  await enter(page);
  await page.evaluate(async()=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok)throw new Error(await r.text());return r.json();
    };
    const settings=await(await fetch('/api/settings')).json();
    settings.data.study_windows=[{start:'19:00',end:'21:00'}];
    await write('/settings',settings,'PUT');
    const d=await write('/drafts/assignment',{items:[{title:'每周禁排练习',due_at:'2026-10-16T21:00:00+08:00'}]});
    const result=await write(`/drafts/${d.id}/confirm`,{revision:d.revision});
    const task=await(await fetch('/api/tasks/'+result.saved_ids[0])).json();
    const step=await write(`/tasks/${task.id}/step-drafts`,{task_revision:task.revision,steps:[{key:'a',title:'做练习',description:'合成',estimated_minutes:120,dependency_keys:[],acceptance_criteria:['完成']}]});
    await write(`/drafts/${step.id}/confirm`,{revision:step.revision});
  });
  await page.getByRole('button',{name:'添加禁排时段'}).click();
  const form=page.getByRole('form',{name:'编辑禁排时段'});
  await form.getByLabel('禁排名称',{exact:true}).fill('每周固定安排');
  await form.getByLabel('禁排开始',{exact:true}).fill('2026-10-14T19:00');
  await form.getByLabel('禁排结束',{exact:true}).fill('2026-10-14T21:00');
  await form.getByLabel('重复方式').selectOption('weekly');
  await form.getByLabel('每周五',{exact:true}).check();
  await form.getByLabel('重复截止日期（可留空）').fill('2026-10-23');
  await form.getByRole('button',{name:'生成禁排草稿'}).click();
  const review=page.getByRole('region',{name:'禁排草稿',exact:true});
  await expect(review.getByLabel('禁排发生预览').locator('p')).toHaveCount(4);
  await expect(review).toContainText('每周三、五');
  expect(await(await page.request.get('/api/scheduling-constraints')).json()).toHaveLength(0);
  await review.screenshot({path:fileURLToPath(new URL('../../docs/roadmap/evidence/weekly-constraints-review.png',import.meta.url))});
  await save(page);
  await page.reload();await page.getByRole('button',{name:'待办与日程',exact:true}).click();
  await expect(page.getByRole('heading',{name:'每周固定安排 · 已启用',exact:true})).toBeVisible();
  await expect(page.locator('.fc-event').filter({hasText:'每周固定安排'})).toHaveCount(2);
  await page.getByRole('button',{name:'一键生成当日日程',exact:true}).click();
  const plan=page.getByRole('region',{name:'智能安排',exact:true});
  await expect(plan).toContainText('仍未安排');
  await expect(plan).toContainText('120 分钟');
  await page.getByRole('button',{name:'智能安排未来 7 天'}).click();
  await expect(plan).toContainText('本次分配 60 分钟');
  const drafts=await(await page.request.get('/api/drafts')).json();
  const generated=drafts.find((d:any)=>d.data.draft_kind==='plan').data.payload;
  expect(generated.blocks).toHaveLength(2);
  expect(generated.blocks.every((b:any)=>b.starts_at.startsWith('2026-10-15'))).toBeTruthy();
  expect(await(await page.request.get('/api/plan-blocks')).json()).toHaveLength(0);
  await plan.getByRole('button',{name:'校对完成，准备保存'}).click();
  await plan.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect.poll(async()=> (await(await page.request.get('/api/plan-blocks')).json()).length).toBe(2);
});

test('weekly series can be amended and disabled on mobile without duplicating rules',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await enter(page);
  await page.getByRole('button',{name:'添加禁排时段'}).click();
  const form=page.getByRole('form',{name:'编辑禁排时段'});
  await form.getByLabel('禁排开始',{exact:true}).fill('2026-10-14T22:00');
  await form.getByLabel('禁排结束',{exact:true}).fill('2026-10-15T02:00');
  await form.getByLabel('重复方式').selectOption('weekly');
  await form.getByRole('button',{name:'生成禁排草稿'}).click();
  const review=page.getByRole('region',{name:'禁排草稿',exact:true});
  await expect(review).toContainText('次日 02:00');
  await expect(review.getByLabel('禁排发生预览').locator('p')).toHaveCount(2);
  await save(page);
  const original=(await(await page.request.get('/api/scheduling-constraints')).json())[0];
  await page.getByRole('button',{name:'修改时段',exact:true}).click();
  await form.getByLabel('每周三',{exact:true}).uncheck();
  await form.getByLabel('每周五',{exact:true}).check();
  await form.getByLabel('重复截止日期（可留空）').fill('2026-10-30');
  await form.getByRole('button',{name:'生成禁排草稿'}).click();
  await expect(review).toContainText('每周五');
  await save(page);
  const changed=await(await page.request.get('/api/scheduling-constraints')).json();
  expect(changed).toHaveLength(1);expect(changed[0].id).toBe(original.id);expect(changed[0].data.weekdays).toEqual([5]);
  await page.getByRole('button',{name:'停用禁排'}).click();
  await expect(page.getByRole('heading',{name:'不可安排 · 已停用'})).toBeVisible();
  await expect(page.locator('.fc-event').filter({hasText:'不可安排'})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
