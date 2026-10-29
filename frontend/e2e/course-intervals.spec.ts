import {test, expect, type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

async function enter(page: Page) {
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button', {name:'创建账号', exact:true}).click();
  await page.getByLabel('邮箱').fill(`intervals-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button', {name:'注册并登录'}).click();
  await expect(page.getByRole('heading', {name:'今天，专注几件事。'})).toBeVisible();
  return page.evaluate(async () => {
    const csrf = (await (await fetch('/api/csrf')).json()).csrf_token;
    const write = async (path:string, body:unknown, method='POST') => {
      const r = await fetch('/api'+path, {method, headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify(body)});
      if(!r.ok) throw new Error(await r.text());
      return r.json();
    };
    const pref = await (await fetch('/api/after-class/preferences')).json();
    await write('/after-class/preferences', {revision:pref.revision, enabled:false}, 'PUT');
    const s = await (await fetch('/api/settings')).json();
    s.data = {...s.data, week1_monday:'2026-10-12', study_windows:[{start:'09:00',end:'12:00'}], periods:{'1':{start:'09:00',end:'09:40'},'2':{start:'10:00',end:'10:40'},'3':{start:'11:00',end:'11:40'}}};
    await write('/settings',s,'PUT');
    const draft = await write('/drafts/timetable',{semester_label:'合成分段课表',courses:[
      {source_key:'split',name:'分段高数',weekday:4,weeks:[1,2],periods:[1,3],location:'A101'},
      {source_key:'adjacent',name:'连堂实验',weekday:5,weeks:[1,2],periods:[1,2],location:'A102'},
    ]});
    await write(`/drafts/${draft.id}/confirm`,{revision:draft.revision});
    const assignment = await write('/drafts/assignment',{items:[{title:'空档练习',due_at:'2026-10-15T12:00:00+08:00'}]});
    const saved = await write(`/drafts/${assignment.id}/confirm`,{revision:assignment.revision});
    const task = await (await fetch('/api/tasks/'+saved.saved_ids[0])).json();
    const steps = await write(`/tasks/${task.id}/step-drafts`,{task_revision:task.revision,steps:[{key:'s',title:'做练习',description:'完成合成练习',estimated_minutes:30,dependency_keys:[],acceptance_criteria:['完成']}]});
    await write(`/drafts/${steps.id}/confirm`,{revision:steps.revision});
    return (await (await fetch('/api/courses')).json());
  });
}

test('nonconsecutive courses leave usable gaps and adjacent breaks are explicitly protected',async({page})=>{
  const before = await enter(page);
  await page.getByRole('button',{name:'课表',exact:true}).click();
  await expect(page.locator('.fc-event').filter({hasText:'分段高数'})).toHaveCount(2);
  await expect(page.locator('.fc-event').filter({hasText:'连堂实验'})).toHaveCount(1);
  await page.locator('.fc-event').filter({hasText:'连堂实验'}).click();
  const detail = page.getByRole('region',{name:'日程详情',exact:true});
  await expect(detail.getByLabel('授课与课间休息')).toContainText('第1节 09:00–09:40');
  await expect(detail.getByLabel('授课与课间休息')).toContainText('第2节 10:00–10:40');
  await expect(detail).toContainText('课间休息（不安排任务）：09:40–10:00');
  await detail.screenshot({path:fileURLToPath(new URL('../../docs/roadmap/evidence/course-intervals-review.png',import.meta.url))});
  await page.getByRole('button',{name:'待办与日程',exact:true}).click();
  await page.getByRole('button',{name:'智能安排未来 7 天'}).click();
  await expect(page.getByRole('region',{name:'智能安排',exact:true}).getByRole('button',{name:'校对完成，准备保存'})).toBeVisible();
  const drafts = await (await page.request.get('/api/drafts')).json();
  const plan = drafts.find((d:any)=>d.data.draft_kind==='plan').data.payload;
  expect(plan.blocks).toHaveLength(1);
  expect(new Date(plan.blocks[0].starts_at).toISOString()).toBe('2026-10-15T01:50:00.000Z');
  expect(new Date(plan.blocks[0].ends_at).toISOString()).toBe('2026-10-15T02:20:00.000Z');
  expect(await (await page.request.get('/api/plan-blocks')).json()).toHaveLength(0);
  const review = page.getByRole('region',{name:'智能安排',exact:true});
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get('/api/plan-blocks')).json()).length).toBe(1);
  expect(await (await page.request.get('/api/courses')).json()).toEqual(before);
});

test('selecting the second segment adjusts the entire occurrence and room-only change preserves the gap',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await enter(page);
  await page.getByRole('button',{name:'课表',exact:true}).click();
  await page.locator('.fc-event').filter({hasText:'分段高数'}).nth(1).click();
  await page.getByRole('button',{name:'调课或停课',exact:true}).click();
  const form = page.getByRole('form',{name:'调整本次课程',exact:true});
  await expect(form.getByLabel('新上课时间')).toHaveValue('2026-10-15T09:00');
  await expect(form.getByLabel('新下课时间')).toHaveValue('2026-10-15T11:40');
  await form.getByLabel('新教室').fill('B202');
  await form.getByLabel('调整依据').fill('教师通知仅本次更换教室');
  await form.getByRole('button',{name:'预览课程调整'}).click();
  const review = page.getByRole('region',{name:'课程调整草稿',exact:true});
  await expect(review).toContainText('本次调课');
  await expect(review).not.toContainText('新时间存在冲突');
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(page.locator('.fc-event').filter({hasText:'分段高数 · B202'})).toHaveCount(2);
  await page.reload();
  await page.getByRole('button',{name:'课表',exact:true}).click();
  await expect(page.locator('.fc-event').filter({hasText:'分段高数 · B202'})).toHaveCount(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
