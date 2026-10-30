import {workspace,inbox} from './workspace';
import { test, expect, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

async function prepare(page:Page, locked=false) {
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`repair-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  const bootstrap=page.waitForResponse(r=>r.url().endsWith('/api/after-class/open')&&r.request().method()==='POST');await page.getByRole('button',{name:'注册并登录'}).click();await (await bootstrap).finished();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
  return page.evaluate(async(locked)=>{
    const csrf=(await (await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok) throw new Error(await r.text()); return r.json();
    };
    const settings=await (await fetch('/api/settings')).json();
    settings.data={...settings.data, study_windows:[{start:'19:00',end:'22:00'}],daily_limit_minutes:180,buffer_minutes:0,max_block_minutes:60};
    await write('/settings',settings,'PUT');
    const a=await write('/drafts/assignment',{items:[{title:'重排练习',due_at:'2026-10-15T22:00:00+08:00'}]});
    const receipt=await write(`/drafts/${a.id}/confirm`,{revision:a.revision});
    const task=await (await fetch('/api/tasks/'+receipt.saved_ids[0])).json();
    const s=await write(`/tasks/${task.id}/step-drafts`,{task_revision:task.revision,steps:[{key:'a',title:'合成步骤',description:'重排验收',estimated_minutes:120,dependency_keys:[],acceptance_criteria:['完成']}]});
    await write(`/drafts/${s.id}/confirm`,{revision:s.revision});
    const plan=await write('/plan-drafts',{horizon_days:7});
    await write(`/drafts/${plan.id}/confirm`,{revision:plan.revision});
    let old=await (await fetch('/api/plan-blocks')).json();
    old.sort((a:any,b:any)=>a.data.starts_at.localeCompare(b.data.starts_at));
    if(locked) await write(`/plan-blocks/${old[0].id}`,{revision:old[0].revision,locked:true},'PATCH');
    await write('/fixed-events',{title:'临时会议',starts_at:old[0].data.starts_at,ends_at:old[0].data.ends_at});
    return (await (await fetch('/api/plan-blocks')).json());
  },locked);
}

test('repairs a calendar conflict after review while retaining the exact unaffected arrangement',async({page})=>{
  const old=await prepare(page);
  await workspace(page,'planning');
  const panel=page.getByRole('region',{name:'日程变化检查',exact:true});
  await expect(panel).toContainText('保留 1 项 · 替换或移除 1 项 · 新增 1 项');
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual(old);
  await panel.getByRole('button',{name:'生成重排草稿',exact:true}).click();
  const review=page.getByRole('region',{name:'计划草稿',exact:true});
  await expect(review).toContainText('确认后移除失效的旧建议');
  await panel.getByRole('button',{name:'生成重排草稿',exact:true}).click();
  expect((await (await page.request.get('/api/drafts')).json()).filter((d:any)=>d.data.draft_kind==='plan')).toHaveLength(1);
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual(old);
  await panel.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.5/e2e/replanning.png',import.meta.url))});

  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
  await expect(panel).toContainText('没有需要替换或新增的安排');
  const blocks=await (await page.request.get('/api/plan-blocks')).json();
  expect(blocks).toHaveLength(2);
  const kept=old.find((b:any)=>b.data.starts_at.includes('12:00:00'));
  expect(kept).toBeTruthy(); expect(blocks.find((b:any)=>b.id===kept.id)).toEqual(kept);
  await page.reload();
  await workspace(page,'planning');
  await expect(panel).toContainText('没有需要替换或新增的安排');
});

test('mobile locked conflict reports a warning without replacing or marking work completed',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const old=await prepare(page,true);
  await workspace(page,'planning');
  const panel=page.getByRole('region',{name:'日程变化检查',exact:true});
  await expect(panel.getByRole('alert').first()).toContainText('解锁');
  await expect(panel.getByRole('button',{name:'生成重排草稿',exact:true})).toBeDisabled();
  expect(await (await page.request.get('/api/plan-blocks')).json()).toEqual(old);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
