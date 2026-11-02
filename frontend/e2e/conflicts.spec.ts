import {workspace,inbox} from './workspace';
import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

async function enter(page:Page){
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`conflicts-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
  await page.evaluate(async()=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok)throw new Error(await r.text());return r.json();
    };
    const pref=await(await fetch('/api/after-class/preferences')).json();
    await write('/after-class/preferences',{revision:pref.revision,enabled:false},'PUT');
    const s=await(await fetch('/api/settings')).json();s.data={...s.data,week1_monday:'2026-10-12',periods:{'1':{start:'09:00',end:'10:00'},'2':{start:'10:10',end:'11:00'}}};
    await write('/settings',s,'PUT');
    const d=await write('/drafts/timetable',{semester_label:'合成冲突课表',courses:[{source_key:'math',name:'五山高数',campus:'五山',weekday:3,weeks:[1],periods:[1]}]});
    await write(`/drafts/${d.id}/confirm`,{revision:d.revision});
  });
  await workspace(page,'courses');
}
async function addDirection(page:Page){
  await workspace(page,'rules');
  await page.getByRole('button',{name:'设置校区转移时间',exact:true}).click();
  const form=page.getByRole('form',{name:'编辑校区转移时间'});
  await form.getByRole('button',{name:'添加一个方向'}).click();
  await form.getByLabel('出发校区').fill('五山');
  await form.getByLabel('到达校区').fill('大学城');
  await form.getByLabel('所需分钟').fill('40');
  await form.getByRole('button',{name:'确认转移时间并保存'}).click();
  await expect.poll(async()=> (await(await page.request.get('/api/settings')).json()).data.campus_transfers.length).toBe(1);
}
async function manual(page:Page){
  await workspace(page,'import');
  await page.getByRole('button',{name:'文字导入',exact:true}).click();
  await page.getByRole('button',{name:'手工添加课程',exact:true}).click();
  const form=page.locator('form').filter({has:page.getByRole('heading',{name:'添加一门课程',exact:true})});
  await form.getByLabel('课程名称').fill('大学城英语');
  await form.getByLabel('校区',{exact:true}).fill('大学城');
  await form.getByLabel('星期').selectOption('3');
  await form.getByLabel('周次（逗号分隔）').fill('1');
  await form.getByLabel('节次（逗号分隔）').fill('2');
  await form.getByRole('button',{name:'生成校对草稿'}).click();
  return page.locator('section').filter({has:page.getByRole('heading',{name:'课表预览',exact:true})});
}

test('directional transfer shortfall is reviewed before a fixed fact is saved and survives reload',async({page})=>{
  await enter(page);await addDirection(page);
  const review=await manual(page);
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await expect(review.getByRole('region',{name:'冲突检查'})).toContainText('需 40 分钟，实际间隔 10 分钟，不足 30 分钟');
  await expect(review.getByRole('button',{name:'确认保存',exact:true})).toBeDisabled();
  expect((await(await page.request.get('/api/courses')).json())).toHaveLength(1);
  await review.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.9/e2e/course-conflicts-review.png',import.meta.url))});
  await review.getByRole('checkbox',{name:'我已核对上述提示，仍按已确认的课程或事项保存'}).check();
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
  await page.reload();await workspace(page,'courses');
  await expect(page.getByRole('region',{name:'冲突检查',exact:true})).toContainText('不足 30 分钟');
  expect((await(await page.request.get('/api/courses')).json())).toHaveLength(2);
});

test('mobile missing direction stays pending and editing the course invalidates its review',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await enter(page);
  const review=await manual(page);
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await expect(review.getByRole('region',{name:'冲突检查'})).toContainText('暂不能判断能否赶上');
  await expect(review.getByRole('button',{name:'确认保存',exact:true})).toBeDisabled();
  await review.getByRole('checkbox',{name:'我已核对上述提示，仍按已确认的课程或事项保存'}).check();
  await expect(review.getByRole('button',{name:'确认保存',exact:true})).toBeEnabled();
  await review.getByLabel('节次',{exact:true}).fill('1');
  await expect(review.getByRole('button',{name:'确认保存',exact:true})).toHaveCount(0);
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await expect(review.getByRole('region',{name:'冲突检查'})).toContainText('时间重叠');
  await expect(review.getByRole('button',{name:'确认保存',exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  expect((await(await page.request.get('/api/courses')).json())).toHaveLength(1);
});

test('fixed event cannot use a conflict review after other fixed facts change',async({page})=>{
  await enter(page);
  await page.evaluate(async()=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    await fetch('/api/drafts/calendar-event',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({title:'合成下午事项',starts_at:'2026-10-14T14:00:00+08:00',ends_at:'2026-10-14T15:00:00+08:00'})});
  });
  await page.reload();await inbox(page);
  const review=page.locator('section').filter({has:page.getByRole('heading',{name:'核对日程事项',exact:true})});
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await page.evaluate(async()=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    await fetch('/api/fixed-events',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({title:'另一端新建会议',starts_at:'2026-10-14T14:30:00+08:00',ends_at:'2026-10-14T15:30:00+08:00'})});
  });
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review.getByRole('alert')).toContainText('重新检查冲突');
  expect((await(await page.request.get('/api/fixed-events')).json())).toHaveLength(1);
  await review.getByRole('button',{name:'继续校对'}).click();
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await expect(review.getByRole('region',{name:'冲突检查'})).toContainText('另一端新建会议');
  await review.getByRole('checkbox').check();
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
});

test('existing course campus can be reviewed and updated without duplicating the course',async({page})=>{
  await enter(page);
  const before=await(await page.request.get('/api/courses')).json();
  await page.locator('.fc-event').filter({hasText:'五山高数'}).click();
  await page.getByRole('button',{name:'补充或修改整门课程校区'}).click();
  const form=page.getByRole('form',{name:'编辑整门课程校区'});
  await form.getByLabel('整门课程校区').fill('大学城');
  await form.getByRole('button',{name:'生成校区校对草稿'}).click();
  const review=page.locator('section').filter({has:page.getByRole('heading',{name:'课表预览',exact:true})});
  expect(await(await page.request.get('/api/courses')).json()).toEqual(before);
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
  const after=await(await page.request.get('/api/courses')).json();
  expect(after).toHaveLength(1);
  expect(after[0].id).toBe(before[0].id);
  expect(after[0].data).toEqual({...before[0].data,campus:'大学城'});
});
