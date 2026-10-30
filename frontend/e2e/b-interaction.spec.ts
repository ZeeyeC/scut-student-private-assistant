import {workspace,inbox,negotiation} from './workspace';
import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

const evidence=(name:string)=>fileURLToPath(new URL(`../../docs/validation/demo2.5.1/e2e/b-interaction/${name}.png`,import.meta.url));
async function enter(page:Page){
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`b-interaction-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录',exact:true}).click();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
}
async function write(page:Page,path:string,body:unknown){
  return page.evaluate(async({path,body})=>{
    const token=(await(await fetch('/api/csrf')).json()).csrf_token;
    const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
    if(!r.ok)throw new Error(await r.text());return r.json();
  },{path,body});
}
async function task(page:Page,due="2026-10-22T22:00:00+08:00"){
  const d=await write(page,'/drafts/assignment',{items:[{title:'交互验收合成练习',due_at:due}]});
  const id=(await write(page,`/drafts/${d.id}/confirm`,{revision:d.revision})).saved_ids[0];
  const t=await(await page.request.get('/api/tasks/'+id)).json();
  const s=await write(page,`/tasks/${id}/step-drafts`,{task_revision:t.revision,steps:[{key:'s',title:'练习步骤',description:'隔离验收',estimated_minutes:60,dependency_keys:[],acceptance_criteria:['完成']}]});
  await write(page,`/drafts/${s.id}/confirm`,{revision:s.revision});return id;
}
test('constraint clarification survives reload and explicit confirmation/deactivation changes only that rule',async({page})=>{
  await enter(page);await page.getByRole('button',{name:'助手',exact:true}).click();
  await page.getByRole('button',{name:'安排持续约束',exact:true}).click();
  const panel=page.getByRole('region',{name:'对话约束意图',exact:true});
  await panel.getByRole('button',{name:'新建禁排意图',exact:true}).click();
  await panel.getByLabel('日期或相对星期').fill('2026-11-04');
  await panel.getByRole('button',{name:'保存候选时间',exact:true}).click();
  await expect(panel).toContainText('开始未知');
  expect(await(await page.request.get('/api/scheduling-constraints')).json()).toEqual([]);
  const initial=await(await page.request.get('/api/constraint-intents')).json();expect(initial).toHaveLength(1);
  await page.reload();await page.getByRole('button',{name:'助手',exact:true}).click();
  await panel.getByRole('button',{name:'补充或修改时间',exact:true}).click();
  await panel.getByLabel('约束开始钟点').fill('14:00');await panel.getByLabel('约束结束钟点').fill('17:00');
  await panel.getByRole('button',{name:'保存候选时间',exact:true}).click();
  await panel.getByRole('button',{name:'生成同一约束草稿',exact:true}).click();
  const draft=panel.getByRole('region',{name:'禁排草稿',exact:true});
  await expect(draft).toContainText('不可安排');expect(await(await page.request.get('/api/scheduling-constraints')).json()).toEqual([]);
  await draft.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(panel).toContainText('规则已确认');
  await panel.screenshot({path:evidence('constraint-confirmed')});
  await panel.getByRole('button',{name:'请求停用已确认规则',exact:true}).click();
  expect((await(await page.request.get('/api/scheduling-constraints')).json())[0].data.active).toBe(true);
  await panel.getByRole('button',{name:'确认停用这条规则',exact:true}).click();await expect(panel).toContainText('规则已停用');
  const after=await(await page.request.get('/api/constraint-intents')).json();expect(after).toHaveLength(1);expect(after[0].id).toBe(initial[0].id);
});
test('negotiation chooses a real plan then cancelling preserves the confirmed schedule',async({page})=>{
  await enter(page);await task(page);await negotiation(page);
  const panel=page.getByRole('region',{name:'多轮规划协商',exact:true});
  await panel.getByLabel('目标与取舍（不必填写私人原因）').fill('先做一小时练习');
  await panel.getByLabel('开始日期',{exact:true}).fill('2026-10-15');await panel.getByLabel('范围天数').fill('2');
  await panel.getByRole('button',{name:'保存协商意图',exact:true}).click();await panel.getByRole('button',{name:'预览可选方案',exact:true}).click();
  const choose=panel.getByRole('button',{name:/选择.+并生成草稿/});await expect(choose.first()).toBeVisible();
  expect(await(await page.request.get('/api/plan-blocks')).json()).toEqual([]);
  await choose.first().click();const review=panel.getByRole('region',{name:'计划草稿',exact:true});
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);await expect(panel).toContainText('所选计划草稿：已确认');const blocks=await(await page.request.get('/api/plan-blocks')).json();expect(blocks.length).toBeGreaterThan(0);
  await panel.getByRole('button',{name:'取消本轮协商',exact:true}).click();expect(await(await page.request.get('/api/plan-blocks')).json()).toEqual(blocks);
  await expect(panel).toContainText('所选计划草稿：已确认');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await panel.screenshot({path:evidence('negotiation-confirmed')});
});
test('weekly acceptance generates a reviewed next week draft and retains confirmed facts on restore',async({page})=>{
  await enter(page);await task(page);await workspace(page,'review');
  const review=page.getByRole('region',{name:'每周复盘',exact:true});await review.getByLabel('选择周内日期').fill('2026-10-12');
  await review.getByLabel('这周遇到的情况，或下周想怎样调整').fill('下周先核对已有练习。');
  await review.getByRole('button',{name:'接受这项调整意向',exact:true}).click();await review.getByRole('button',{name:'生成下周计划草稿',exact:true}).click();
  const plan=review.getByRole('region',{name:'计划草稿',exact:true});await expect(plan).toBeVisible();
  expect(await(await page.request.get('/api/plan-blocks')).json()).toEqual([]);
  await plan.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toContainText('已确认快照');const before=await(await page.request.get('/api/plan-blocks')).json();
  await review.getByRole('button',{name:'恢复为待选择',exact:true}).click();expect(await(await page.request.get('/api/plan-blocks')).json()).toEqual(before);
  await review.screenshot({path:evidence('weekly-confirmed')});
});
test('proactive preferences are explicit, survive reload and stay silent',async({page})=>{
  await enter(page);const tid=await task(page,'2026-10-15T22:00:00+08:00');await workspace(page,'reminders');
  const panel=page.getByRole('region',{name:'主动建议设置',exact:true});await expect(panel).toContainText('已关闭');
  await panel.getByRole('button',{name:'编辑主动建议设置',exact:true}).click();await panel.getByLabel('开启主动建议',{exact:true}).check();
  await panel.getByLabel('安静时段时区（未知可留空）').fill('Asia/Shanghai');await panel.getByLabel('安静时段设置',{exact:true}).selectOption('none');
  await panel.getByRole('button',{name:'确认保存主动建议设置',exact:true}).click();await expect(panel).toContainText('已开启');
  await page.reload();await workspace(page,'reminders');await expect(panel).toContainText('已开启');await expect(panel).toContainText('已明确不设安静时段');
  await panel.screenshot({path:evidence('proactive-settings')});
  await inbox(page,'建议');
  const suggestions=page.getByRole('region',{name:'主动建议',exact:true});
  await suggestions.getByRole('button',{name:'刷新建议',exact:true}).click();
  await suggestions.getByRole('button',{name:'打开关联任务详情',exact:true}).first().click();
  const detail=page.getByRole('dialog',{name:'交互验收合成练习',exact:true});await expect(detail).toContainText('交互验收合成练习');
  expect((await(await page.request.get('/api/tasks/'+tid)).json()).data.status).toBe('open');

});

test('chat approval displays real conflicts and requires explicit acknowledgement before saving',async({page})=>{
  await enter(page);
  const fact={title:'已确认合成事项',starts_at:'2026-11-04T14:00:00+08:00',ends_at:'2026-11-04T15:00:00+08:00'};
  const first=await write(page,'/drafts/calendar-event',fact);await write(page,`/drafts/${first.id}/confirm`,{revision:first.revision});
  const draft=await write(page,'/drafts/calendar-event',{...fact,title:'待核对合成事项'});
  await page.getByRole('button',{name:'助手',exact:true}).click();
  await page.getByLabel('给助手的消息').fill('commit:'+draft.id);await page.getByRole('button',{name:'发送',exact:true}).click();
  const approval=page.getByRole('region',{name:'助手操作确认',exact:true});
  await expect(approval.getByRole('region',{name:'冲突检查',exact:true})).toContainText('1 项冲突');
  await expect(approval.getByRole('button',{name:'批准并执行',exact:true})).toBeDisabled();
  expect(await(await page.request.get('/api/fixed-events')).json()).toHaveLength(1);
  await approval.getByLabel('我已核对当前冲突和未知信息，仍按这些事实保存').check();
  await approval.screenshot({path:evidence('chat-conflict-review')});
  await approval.getByRole('button',{name:'批准并执行',exact:true}).click();await expect(approval).toHaveCount(0);
  await expect.poll(async()=> (await(await page.request.get('/api/fixed-events')).json()).length).toBe(2);
  const saved=await(await page.request.get(`/api/drafts/${draft.id}`)).json();expect(saved.data.summary.conflict_reviewed).toBe(true);
});
