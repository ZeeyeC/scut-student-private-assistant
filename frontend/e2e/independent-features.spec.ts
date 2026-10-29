import {test,expect,type Page} from "@playwright/test";
import { fileURLToPath } from "node:url";

const evidence=(name:string)=>fileURLToPath(new URL(`../../docs/roadmap/evidence/independent/${name}.png`,import.meta.url));

async function enter(page:Page) {
  await page.clock.setFixedTime(new Date("2026-10-14T10:30:00Z"));
  await page.goto("/");
  await page.getByRole("button",{name:"创建账号",exact:true}).click();
  await page.getByLabel("邮箱").fill(`independent-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button",{name:"注册并登录"}).click();
  await expect(page.getByRole("heading",{name:"今天，专注几件事。"})).toBeVisible();
}

async function seed(page:Page) {
  return page.evaluate(async()=>{
    const token=(await(await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok)throw new Error(await r.text());return r.json();
    };
    const d=await write('/drafts/assignment',{items:[{title:'独立功能合成练习',due_at:'2026-10-20T22:00:00+08:00'}]});
    const tid=(await write(`/drafts/${d.id}/confirm`,{revision:d.revision})).saved_ids[0];
    const task=await(await fetch(`/api/tasks/${tid}`)).json();
    const s=await write(`/tasks/${tid}/step-drafts`,{task_revision:task.revision,steps:[{key:'one',title:'合成步骤',description:'隔离资料',estimated_minutes:60,dependency_keys:[],acceptance_criteria:['完成']}]});
    await write(`/drafts/${s.id}/confirm`,{revision:s.revision});
    const p=await write('/plan-drafts',{scope:'today'});
    await write(`/drafts/${p.id}/confirm`,{revision:p.revision});
    return tid;
  });
}

test('timer pauses, resumes after reload and switches to manual exactly once',async({page})=>{
  await enter(page);const tid=await seed(page);await page.reload();
  const feedback=page.getByRole('region',{name:'本次安排执行反馈',exact:true});
  const timer=feedback.getByRole('region',{name:'自愿计时',exact:true});
  await timer.getByRole('button',{name:'开始计时',exact:true}).click();
  await expect(timer.getByRole('timer')).toContainText('计时中');
  await timer.getByRole('button',{name:'暂停计时',exact:true}).click();
  await expect(timer.getByRole('timer')).toContainText('已暂停');
  await page.screenshot({path:evidence('timer-paused'),fullPage:true});
  await page.reload();
  await expect(timer.getByRole('timer')).toContainText('已暂停');
  await timer.getByRole('button',{name:'继续计时',exact:true}).click();
  await timer.getByLabel('改为手工补记，替代本次计时投入').check();
  await timer.getByLabel('补记实际分钟').fill('25');
  await timer.getByLabel('计时后的任务状态').selectOption('open');
  await timer.getByRole('button',{name:'结束并保存反馈',exact:true}).click();
  await expect(feedback).toContainText('已记录实际：25 分钟');
  const records=await(await page.request.get(`/api/tasks/${tid}/executions`)).json();
  expect(records).toHaveLength(1);expect(records[0].data.source).toBe('manual');
  expect((await(await page.request.get(`/api/tasks/${tid}`)).json()).data.status).toBe('open');
});

test('confirmed profile survives reload and reset preserves task facts',async({page})=>{
  await enter(page);const tid=await seed(page);
  await page.getByRole('button',{name:'设置',exact:true}).click();
  const profile=page.getByRole('region',{name:'用户偏好与精力档案'});
  await expect(profile).toContainText('未知（未设置）');
  await profile.getByRole('button',{name:'编辑偏好',exact:true}).click();
  await profile.getByLabel('IANA 时区').fill('Asia/Shanghai');
  await profile.getByLabel('专注时长（5–240 分钟）').fill('45');
  await profile.getByLabel('休息时长（0–120 分钟）').fill('0');
  await profile.getByRole('button',{name:'确认并保存偏好',exact:true}).click();
  await expect(profile).toContainText('45 分钟');
  await page.screenshot({path:evidence('profile-confirmed'),fullPage:true});
  expect((await(await page.request.get('/api/profile')).json()).data.preferences.break_minutes).toBe(0);
  await page.reload();await page.getByRole('button',{name:'设置',exact:true}).click();
  await expect(profile).toContainText('45 分钟');
  await profile.getByRole('button',{name:'重置档案',exact:true}).click();
  await profile.getByRole('button',{name:'确认重置偏好',exact:true}).click();
  await expect(profile).toContainText('未知（未设置）');
  expect((await page.request.get(`/api/tasks/${tid}`)).ok()).toBeTruthy();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('goal pause preserves completed subtasks while capacity stays unknown',async({page})=>{
  await enter(page);const tid=await seed(page);
  await page.getByRole('button',{name:'目标与复盘',exact:true}).click();
  const goals=page.getByRole('region',{name:'长期目标',exact:true});
  await goals.getByRole('button',{name:'新建目标',exact:true}).click();
  await goals.getByLabel('目标名称').fill('合成英语目标');
  await goals.getByLabel('每周预算（整数分钟，0 表示本周不投入）').fill('600');
  await goals.getByLabel('负荷类别').selectOption('study');
  await goals.getByLabel('允许的调整').selectOption('reduce');
  await goals.getByRole('button',{name:'添加子任务',exact:true}).click();
  await goals.getByLabel('子任务名称').fill('完成一组练习');
  await goals.getByLabel('预计分钟',{exact:true}).fill('30');
  await goals.getByLabel('状态').selectOption('completed');
  await goals.getByLabel('关联现有任务（可选）').selectOption(tid);
  await goals.getByRole('button',{name:'确认并保存目标',exact:true}).click();
  await goals.getByRole('button',{name:'暂停目标',exact:true}).click();
  await expect(goals).toContainText('已暂停');await expect(goals).toContainText('容量未知');
  await page.screenshot({path:evidence('goal-paused'),fullPage:true});
  const saved=await(await page.request.get('/api/goals')).json();
  expect(saved.goals[0].data.paused).toBe(true);
  expect(saved.goals[0].data.completion_history).toHaveLength(1);
  expect((await(await page.request.get('/api/tasks')).json())).toHaveLength(1);
});

test('weekly review reads actual25 and accepts an intent without changing the plan',async({page})=>{
  await enter(page);const tid=await seed(page);
  await page.evaluate(async(id)=>{
    const [task,steps,blocks,token]=await Promise.all([fetch(`/api/tasks/${id}`).then(r=>r.json()),fetch(`/api/tasks/${id}/steps`).then(r=>r.json()),fetch('/api/plan-blocks').then(r=>r.json()),fetch('/api/csrf').then(r=>r.json())]);
    const r=await fetch('/api/executions',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token.csrf_token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({client_operation_id:crypto.randomUUID(),execution_id:crypto.randomUUID(),task_id:id,task_revision:task.revision,step_id:steps[0].id,step_revision:steps[0].revision,plan_block_id:blocks[0].id,plan_block_revision:blocks[0].revision,performed_on:'2026-10-14',timezone:'Asia/Shanghai',actual_minutes:25,feedback:'partial',unfinished_reason:'insufficient_time'})});
    if(!r.ok)throw new Error(await r.text());
  },tid);
  const before=await(await page.request.get('/api/plan-blocks')).json();
  await page.getByRole('button',{name:'目标与复盘',exact:true}).click();
  const review=page.getByRole('region',{name:'每周复盘',exact:true});
  await review.getByLabel('选择周内日期').fill('2026-10-12');
  await expect(review).toContainText('25 分钟');
  await review.getByLabel('这周遇到的情况，或下周想怎样调整').fill('下周希望将练习拆成两次，先核对可用时间。');
  await review.getByRole('button',{name:'接受这项调整意向',exact:true}).click();
  const report=await(await page.request.get('/api/weekly-review?week_start=2026-10-12&timezone=Asia%2FShanghai')).json();
  expect(report.execution.actual_seconds).toBe(1500);
  expect(report.review.data.status).toBe('accepted_pending_integration');
  expect(await(await page.request.get('/api/plan-blocks')).json()).toEqual(before);
  await page.screenshot({path:evidence('weekly-intent'),fullPage:true});
});
