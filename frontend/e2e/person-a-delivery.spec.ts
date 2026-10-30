import {workspace,inbox,negotiation} from './workspace';
import {test,expect,type Page} from '@playwright/test';

async function get(page:Page,path:string){return (await page.request.get('/api'+path)).json();}
async function write(page:Page,path:string,body:unknown,method='POST') {
  return page.evaluate(async({path,body,method})=>{
    const token=(await(await fetch('/api/csrf')).json()).csrf_token;
    const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
    if(!r.ok)throw new Error(await r.text());return r.json();
  },{path,body,method});
}
async function enter(page:Page) {
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`a-delivery-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录',exact:true}).click();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
}
async function seed(page:Page) {
  const settings=await get(page,'/settings');
  settings.data={...settings.data,study_windows:[{start:'19:00',end:'22:00'}],daily_limit_minutes:180,buffer_minutes:0};
  await write(page,'/settings',settings,'PUT');
  const a=await write(page,'/drafts/assignment',{items:[{title:'甲乙联合练习',due_at:'2026-10-15T22:00:00+08:00'}]});
  const taskId=(await write(page,`/drafts/${a.id}/confirm`,{revision:a.revision})).saved_ids[0];
  const task=await get(page,`/tasks/${taskId}`);
  const s=await write(page,`/tasks/${taskId}/step-drafts`,{task_revision:task.revision,steps:[{key:'s',title:'联合步骤',description:'合成验收',estimated_minutes:60,dependency_keys:[],acceptance_criteria:['完成']}]});
  await write(page,`/drafts/${s.id}/confirm`,{revision:s.revision});
  return {taskId,stepId:(await get(page,`/tasks/${taskId}/steps`))[0].id};
}

test('generated duration flows through B acceptance and restore without automatic edits',async({page})=>{
  await enter(page);const {taskId,stepId}=await seed(page);
  for(let i=0;i<3;i++){
    const task=await get(page,`/tasks/${taskId}`),step=(await get(page,`/tasks/${taskId}/steps`))[0];
    await write(page,'/executions',{client_operation_id:crypto.randomUUID(),execution_id:crypto.randomUUID(),task_id:taskId,task_revision:task.revision,step_id:stepId,step_revision:step.revision,performed_on:'2026-10-14',timezone:'Asia/Shanghai',actual_minutes:25,feedback:i===2?'completed':'partial',task_status:'open'});
  }
  await inbox(page,'时长');
  const panel=page.getByRole('region',{name:'时长建议',exact:true});
  await panel.getByRole('button',{name:'检查并生成时长建议',exact:true}).click();
  await expect(panel).toContainText('建议：75 分钟');
  expect((await get(page,`/tasks/${taskId}/steps`))[0].data.estimated_minutes).toBe(60);
  await panel.getByRole('button',{name:'接受此时长',exact:true}).click();
  await expect(panel.getByRole('button',{name:'恢复原默认时长',exact:true})).toBeVisible();
  expect((await get(page,`/tasks/${taskId}/steps`))[0].data.estimated_minutes).toBe(75);
  await panel.getByRole('button',{name:'恢复原默认时长',exact:true}).click();
  await expect(panel).toContainText('已恢复默认');
  expect((await get(page,`/tasks/${taskId}/steps`))[0].data.estimated_minutes).toBe(60);
  await panel.getByRole('button',{name:'检查并生成时长建议',exact:true}).click();
  await expect(panel).toContainText('本次未生成建议');
  expect((await get(page,'/duration-suggestions')).suggestions).toHaveLength(1);
});

test('active changes are durable and still require original plan confirmation',async({page})=>{
  await enter(page);await seed(page);await workspace(page,'planning');
  const panel=page.getByRole('region',{name:'日程变化检查',exact:true});
  await expect(panel).toContainText('变化建议：待校对');expect(await get(page,'/plan-blocks')).toEqual([]);
  await panel.getByRole('button',{name:'忽略本次变化建议',exact:true}).click();await expect(panel).toContainText('已忽略本次结果');
  await page.reload();await workspace(page,'planning');await expect(panel).toContainText('已忽略本次结果');
  await write(page,'/fixed-events',{title:'合成临时事项',starts_at:'2026-10-14T19:00:00+08:00',ends_at:'2026-10-14T19:30:00+08:00'});
  await panel.getByRole('button',{name:'检查日程变化',exact:true}).click();await expect(panel).toContainText('变化建议：待校对');
  await panel.getByRole('button',{name:'生成重排草稿',exact:true}).click();
  const review=page.getByRole('region',{name:'计划草稿',exact:true});await expect(review).toBeVisible();expect(await get(page,'/plan-blocks')).toEqual([]);
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);await expect(panel).toContainText('变化建议：已确认');
  await panel.getByRole('button',{name:'检查日程变化',exact:true}).click();await expect(panel).toContainText('没有需要替换或新增的安排');
});

test('confirmed profile and goal affect actual options and show evidence',async({page})=>{
  await enter(page);const {taskId}=await seed(page);const profile=await get(page,'/profile');
  await write(page,'/profile',{revision:profile.revision,data:{timezone:'UTC',preferences:{preferred_study_windows:[{weekdays:[3],start:'13:00',end:'14:00',task_type:'any'}],focus_minutes:25,break_minutes:10,daily_load_minutes:50}}},'PUT');
  await write(page,'/goals',{title:'共享练习目标',weekly_budget_minutes:50,priority:3,load_category:'study',allowed_adjustment:'reduce',subtasks:[{title:'关联练习',status:'open',estimated_minutes:60,task_id:taskId}]});
  await workspace(page,'planning');const panel=page.getByRole('region',{name:'规划方案与日常候选',exact:true});
  await expect(panel.getByRole('article',{name:'遵循软偏好',exact:true})).toContainText('偏好内 50 分钟');
  await panel.getByText('查看执行、档案和目标依据',{exact:true}).click();
  await expect(panel).toContainText('完整实际总量 未知');await expect(panel).toContainText('来源 user');await expect(panel).toContainText('时区 UTC');await expect(panel).toContainText('预算 50 分钟');
  const options=await get(page,'/planning-options');expect(options.options[0].blocks[0].starts_at).not.toBe(options.options[1].blocks[0].starts_at);expect(await get(page,'/plan-blocks')).toEqual([]);
});

test('negotiation waits for current source revision while cached settings refresh',async({page})=>{
  await enter(page);await seed(page);let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/settings',async route=>{if(route.request().method()==='GET')await gate;await route.continue();});
  await negotiation(page);const panel=page.getByRole('region',{name:'多轮规划协商',exact:true});
  await expect(panel.getByRole('button',{name:'保存协商意图',exact:true})).toBeDisabled();release();
  await panel.getByLabel('目标与取舍（不必填写私人原因）').fill('按最新资料安排');await panel.getByLabel('开始日期',{exact:true}).fill('2026-10-15');
  await panel.getByRole('button',{name:'保存协商意图',exact:true}).click();await expect(panel.getByRole('button',{name:'预览可选方案',exact:true})).toBeVisible();await expect(panel.getByRole('alert')).toHaveCount(0);
});
