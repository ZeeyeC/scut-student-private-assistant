import {workspace,inbox} from './workspace';
import { test, expect } from '@playwright/test';

test('shared calendar filters fixed courses; smart schedule includes facts and never moves them', async ({page})=>{
  // This fixture's timetable and planner clock are fixed to the same teaching week.
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`split-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
  const before=await page.evaluate(async()=>{
    const csrf=(await (await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok) throw new Error(await r.text()); return r.json();
    };
    const settings=await (await fetch('/api/settings')).json();
    settings.data={...settings.data,week1_monday:'2026-10-12',periods:{'1':{start:'09:00',end:'10:00'}},study_windows:[{start:'09:00',end:'12:00'}]};
    await write('/settings',settings,'PUT');
    const course=await write('/drafts/timetable',{semester_label:'固定课表',courses:[{source_key:'fixed',name:'固定高数课',weekday:4,weeks:[1],periods:[1]}]});
    await write(`/drafts/${course.id}/confirm`,{revision:course.revision});
    await write('/fixed-events',{title:'单独固定事项',starts_at:'2026-10-15T10:30:00+08:00',ends_at:'2026-10-15T11:00:00+08:00'});
    const task=await write('/drafts/assignment',{items:[{title:'智能排程任务'}]});
    await write(`/drafts/${task.id}/confirm`,{revision:task.revision});
    const saved=(await (await fetch('/api/tasks')).json())[0];
    const steps=await write(`/tasks/${saved.id}/step-drafts`,{task_revision:saved.revision,steps:[{key:'s',title:'完成练习',description:'完成练习要求',estimated_minutes:30,dependency_keys:[],acceptance_criteria:['完成']}]});
    await write(`/drafts/${steps.id}/confirm`,{revision:steps.revision});
    return (await (await fetch('/api/courses')).json());
  });
  await workspace(page,'courses');
  await expect(page.getByRole('heading',{name:'日程',exact:true})).toBeVisible();
  await expect(page.locator('.fc-event').filter({hasText:'固定高数课'})).toHaveCount(1);
  await expect(page.locator('.fc-event').filter({hasText:'单独固定事项'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'智能安排未来 7 天'})).toBeHidden();
  await page.getByRole('button',{name:'导入课表',exact:true}).click();await page.getByRole('button',{name:'文字导入',exact:true}).click();await expect(page.getByRole('button',{name:'手工添加课程',exact:true})).toBeVisible();await page.keyboard.press('Escape');
  await page.screenshot({path:'/private/tmp/demo21-fixed-timetable.png',fullPage:true});
  await workspace(page,'planning');
  await expect(page.getByRole('dialog',{name:'安排学习',exact:true})).toBeVisible();
  await expect(page.locator('.fc-event').filter({hasText:'固定高数课'})).toHaveCount(1);
  await expect(page.locator('.fc-event').filter({hasText:'单独固定事项'})).toHaveCount(1);
  await expect(page.getByRole('button',{name:'手工添加课程',exact:true})).toBeHidden();
  await page.getByRole('button',{name:'智能安排未来 7 天'}).click();
  await expect(page.getByRole('heading',{name:'未来 7 天计划'})).toBeVisible();
  const drafts=await (await page.request.get('/api/drafts')).json();
  const plan=drafts.find((d:any)=>d.data.draft_kind==='plan').data.payload;
  expect(plan.blocks.length).toBeGreaterThan(0);
  for(const b of plan.blocks) for(const fixed of plan.fixed_agenda) {
    expect(new Date(b.ends_at)<=new Date(fixed.starts_at) || new Date(b.starts_at)>=new Date(fixed.ends_at)).toBeTruthy();
  }
  expect(await (await page.request.get('/api/plan-blocks')).json()).toHaveLength(0);
  await page.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get('/api/plan-blocks')).json()).length).toBeGreaterThan(0);
  expect(await (await page.request.get('/api/courses')).json()).toEqual(before);
  await page.screenshot({path:'/private/tmp/demo21-todos-schedule.png',fullPage:true});
  await expect(page.locator('.fc-event').filter({hasText:'智能排程任务'})).toHaveCount(1);
  await workspace(page,'courses');
  await expect(page.locator('.fc-event').filter({hasText:'智能排程任务'})).toHaveCount(0);
  await expect(page.locator('.fc-event').filter({hasText:'固定高数课'})).toHaveCount(1);
});
