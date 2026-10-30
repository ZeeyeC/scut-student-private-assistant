import {workspace,inbox} from './workspace';
import {test, expect, type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

async function write(page:Page,path:string,body:unknown,method='POST') {
  return page.evaluate(async({path,body,method})=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
    if(!r.ok)throw new Error(await r.text());return r.json();
  },{path,body,method});
}

test('explicit classification persists and a matching lab rule creates only a reviewable candidate',async({page})=>{
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`types-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录',exact:true}).click();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
  const pref=await(await page.request.get('/api/after-class/preferences')).json();
  await write(page,'/after-class/preferences',{revision:pref.revision,enabled:false},'PUT');
  const s=await(await page.request.get('/api/settings')).json();
  s.data={...s.data,week1_monday:'2026-10-12',week_count:4,periods:{'1':{start:'19:00',end:'20:00'}}};
  await write(page,'/settings',s,'PUT');
  const d=await write(page,'/drafts/timetable',{semester_label:'合成类型验收',courses:[{source_key:'explicit-lab',name:'合成实验课程',weekday:4,weeks:[1],periods:[1],location:'101',campus:'主校区'}]});
  await write(page,`/drafts/${d.id}/confirm`,{revision:d.revision});
  await workspace(page,'courses');await page.locator('.fc-event').filter({hasText:'合成实验课程'}).click();
  const types=page.getByRole('region',{name:'课程与任务类型',exact:true});
  await expect(types).toContainText('未知（未分类）');
  await types.getByRole('article',{name:'类型：合成实验课程',exact:true}).getByRole('button',{name:'设置类型',exact:true}).click();
  await types.getByLabel('明确类型',{exact:true}).selectOption('lab');
  await types.getByRole('button',{name:'确认保存类型',exact:true}).click();
  await expect(types.getByRole('article',{name:'类型：合成实验课程',exact:true})).toContainText('实验课');
  await page.reload();await workspace(page,'courses');await page.locator('.fc-event').filter({hasText:'合成实验课程'}).click();
  await expect(types.getByRole('article',{name:'类型：合成实验课程',exact:true})).toContainText('实验课');
  await workspace(page,'planning');
  const panel=page.getByRole('region',{name:'规划方案与日常候选',exact:true});
  await panel.getByRole('button',{name:'添加课程类型规则',exact:true}).click();
  await panel.getByLabel('该类型课前准备分钟1',{exact:true}).fill('20');
  await panel.getByLabel('上述规则由我明确指定，仅生成待确认候选',{exact:true}).check();
  await panel.getByRole('button',{name:'预览日常候选',exact:true}).click();
  const candidates=panel.getByLabel('日常候选列表');
  await expect(candidates).toContainText('合成实验课程 · 课前准备');
  await panel.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.5/e2e/course-type-candidates.png',import.meta.url))});
  expect(await(await page.request.get('/api/fixed-events')).json()).toEqual([]);
  await candidates.getByRole('button',{name:'校对此候选',exact:true}).click();
  await expect(page.getByText('合成实验课程 · 课前准备',{exact:true}).last()).toBeVisible();
  expect(await(await page.request.get('/api/fixed-events')).json()).toEqual([]);
  const drafts=await(await page.request.get('/api/drafts')).json();
  const candidate=drafts.find((x:any)=>x.data.source.routine_candidate_id);
  expect(candidate.data.source.candidate_basis).toMatchObject({course_type:'lab',minutes:20,rule_source:'explicit_course_type_rule'});
});
