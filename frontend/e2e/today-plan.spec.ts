import { test, expect, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

async function enter(page: Page) {
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`today-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('heading',{name:'今天，专注几件事。'})).toBeVisible();
}

async function seed(page: Page) {
  return page.evaluate(async()=>{
    const csrf=(await (await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok) throw new Error(await r.text()); return r.json();
    };
    const settings=await (await fetch('/api/settings')).json();
    settings.data={...settings.data,week1_monday:'2026-10-12',study_windows:[{start:'18:00',end:'22:00'}],daily_limit_minutes:240,periods:{'1':{start:'19:00',end:'20:00'}}};
    await write('/settings',settings,'PUT');
    const course=await write('/drafts/timetable',{semester_label:'当日合成',courses:[{source_key:'fixed',name:'晚间固定课程',weekday:3,weeks:[1],periods:[1]}]});
    await write(`/drafts/${course.id}/confirm`,{revision:course.revision});
    const constraint=await write('/drafts/scheduling-constraint',{constraint:{title:'晚间休息',timezone:'Asia/Shanghai',starts_at:'2026-10-14T20:00:00+08:00',ends_at:'2026-10-14T20:30:00+08:00'}});
    await write(`/drafts/${constraint.id}/confirm`,{revision:constraint.revision});
    const assignment=await write('/drafts/assignment',{items:[{title:'今日练习',due_at:'2026-10-17T22:00:00+08:00'}]});
    const saved=await write(`/drafts/${assignment.id}/confirm`,{revision:assignment.revision});
    const task=await (await fetch(`/api/tasks/${saved.saved_ids[0]}`)).json();
    const step=await write(`/tasks/${task.id}/step-drafts`,{task_revision:task.revision,steps:[{key:'a',title:'今日练习步骤',description:'合成验收',estimated_minutes:180,dependency_keys:[],acceptance_criteria:['完成']}]});
    await write(`/drafts/${step.id}/confirm`,{revision:step.revision});
    return (await (await fetch('/api/courses')).json());
  });
}

test('today preview avoids fixed courses and protection, saves only after review and survives reload',async({page})=>{
  await enter(page);
  const courses=await seed(page);
  await page.getByRole('button',{name:'一键生成当日日程',exact:true}).click();
  const review=page.getByRole('region',{name:'计划草稿',exact:true});
  await expect(review.getByRole('heading',{name:'2026-10-14 当日日程'})).toBeVisible();
  await expect(review).toContainText('未自动延至明天');
  await expect(review).toContainText('晚间固定课程');
  await expect(review).toContainText('晚间休息');
  const drafts=await (await page.request.get('/api/drafts')).json();
  const p=drafts.find((d:any)=>d.data.draft_kind==='plan').data.payload;
  expect(p.scope).toBe('today'); expect(p.horizon_days).toBe(1);
  expect(p.blocks.length).toBeGreaterThan(0);
  for(const b of p.blocks){
    expect(new Date(b.starts_at)>=new Date('2026-10-14T18:30:00+08:00')).toBeTruthy();
    expect(new Date(b.ends_at)<=new Date('2026-10-15T00:00:00+08:00')).toBeTruthy();
    for(const fixed of [...p.fixed_agenda,...p.protected_windows.map((r:any)=>r.data)])
      expect(new Date(b.ends_at)<=new Date(fixed.starts_at)||new Date(b.starts_at)>=new Date(fixed.ends_at)).toBeTruthy();
  }
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual([]);
  await page.reload();
  await expect(review.getByRole('heading',{name:'2026-10-14 当日日程'})).toBeVisible();
  await review.screenshot({path:fileURLToPath(new URL('../../docs/roadmap/evidence/today-plan-review.png',import.meta.url))});
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual([]);
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
  await expect.poll(async()=>(await (await page.request.get('/api/plan-blocks')).json()).length).toBe(p.blocks.length);
  expect(await (await page.request.get('/api/courses')).json()).toEqual(courses);
  await page.reload();
  await expect(page.getByRole('heading',{name:'今日练习',exact:true}).first()).toBeVisible();
  const saved=await (await page.request.get('/api/plan-blocks')).json();
  const exports=await (await page.request.get('/api/data-export')).json();
  expect(exports.resources.filter((r:any)=>r.kind==='plan_snapshot')).toHaveLength(1);
  expect(saved.every((b:any)=>new Date(b.data.starts_at).toISOString().startsWith('2026-10-14'))).toBeTruthy();
});

test('schedule offers both modes; an empty day shows why without fabricating work',async({page})=>{
  await enter(page);
  await page.getByRole('button',{name:'待办与日程',exact:true}).click();
  const schedule=page.getByRole('region',{name:'智能安排',exact:true});
  await expect(schedule.getByRole('button',{name:'智能安排未来 7 天'})).toBeVisible();
  await schedule.getByRole('button',{name:'一键生成当日日程',exact:true}).click();
  const review=page.getByRole('region',{name:'计划草稿',exact:true});
  await expect(review).toContainText('当前没有需要新安排的步骤');
  await expect(review.getByRole('button',{name:'校对完成，准备保存'})).toHaveCount(0);
  await expect(review).toContainText('没有可保存的安排');
  await schedule.getByRole('button',{name:'智能安排未来 7 天'}).click();
  await expect(review.getByRole('heading',{name:'未来 7 天计划'})).toBeVisible();
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual([]);
});
