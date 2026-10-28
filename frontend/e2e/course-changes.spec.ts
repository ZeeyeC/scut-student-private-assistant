import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

async function enter(page:Page){
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`change-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('heading',{name:'今天，专注几件事。'})).toBeVisible();
  const courses=await page.evaluate(async()=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok)throw new Error(await r.text());return r.json();
    };
    const pref=await(await fetch('/api/after-class/preferences')).json();
    await write('/after-class/preferences',{revision:pref.revision,enabled:false},'PUT');
    const s=await(await fetch('/api/settings')).json();s.data={...s.data,week1_monday:'2026-10-12',periods:{'1':{start:'09:00',end:'10:00'},'2':{start:'10:00',end:'11:00'}}};
    await write('/settings',s,'PUT');
    const d=await write('/drafts/timetable',{semester_label:'合成调课',courses:[
      {source_key:'math',name:'待调整高数',weekday:3,weeks:[1,2],periods:[1],location:'A101'},
      {source_key:'other',name:'周四固定英语',weekday:4,weeks:[1,2],periods:[2]},
    ]});
    await write(`/drafts/${d.id}/confirm`,{revision:d.revision});
    return(await(await fetch('/api/courses')).json());
  });
  await page.getByRole('button',{name:'课表',exact:true}).click();
  return courses;
}
async function save(page:Page){
  const r=page.getByRole('region',{name:'课程调整草稿',exact:true});
  await r.getByRole('button',{name:'校对完成，准备保存'}).click();
  await r.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(r).toHaveCount(0);
}
async function select(page:Page){
  await page.locator('.fc-event').filter({hasText:'待调整高数'}).click();
  await page.getByRole('button',{name:'调课或停课',exact:true}).click();
  return page.getByRole('form',{name:'调整本次课程',exact:true});
}

test('one occurrence moves after review, warns about overlaps, preserves the next week and restores',async({page})=>{
  const courses=await enter(page);
  const original=await(await page.request.get('/api/occurrences?start=2026-10-12&end=2026-10-25')).json();
  const form=await select(page);
  await form.getByLabel('新上课时间').fill('2026-10-15T10:00');
  await form.getByLabel('新下课时间').fill('2026-10-15T11:00');
  await form.getByLabel('新教室').fill('B202');
  await form.getByLabel('调整依据').fill('教师通知：本周改至周四上午，下一周不变');
  await form.getByRole('button',{name:'预览课程调整'}).click();
  const review=page.getByRole('region',{name:'课程调整草稿',exact:true});
  await expect(review).toContainText('周四固定英语');
  await expect(review).toContainText('新时间存在冲突');
  expect(await(await page.request.get('/api/course-changes')).json()).toEqual([]);
  expect(await(await page.request.get('/api/occurrences?start=2026-10-12&end=2026-10-25')).json()).toEqual(original);
  await page.reload();await page.getByRole('button',{name:'课表',exact:true}).click();
  await expect(review).toContainText('教师通知');
  await review.screenshot({path:fileURLToPath(new URL('../../docs/roadmap/evidence/course-change-review.png',import.meta.url))});
  await save(page);
  const changed=await(await page.request.get('/api/occurrences?start=2026-10-12&end=2026-10-25')).json();
  expect(changed.find((e:any)=>e.title==='待调整高数'&&e.original_date==='2026-10-14').starts_at).toContain('2026-10-15T10:00');
  expect(changed.find((e:any)=>e.title==='待调整高数'&&e.original_date==='2026-10-21')).toEqual(original.find((e:any)=>e.title==='待调整高数'&&e.original_date==='2026-10-21'));
  expect(await(await page.request.get('/api/courses')).json()).toEqual(courses);
  const history=page.getByRole('region',{name:'已确认课程调整',exact:true});
  await expect(history).toContainText('B202');
  await history.getByRole('button',{name:'恢复原课（先预览）'}).click();
  await expect(review.getByRole('heading',{name:'待调整高数 · 恢复原课'})).toBeVisible();
  await save(page);
  expect(await(await page.request.get('/api/occurrences?start=2026-10-12&end=2026-10-25')).json()).toEqual(original);
  await expect(history).toContainText('已恢复原课');
});

test('mobile cancellation retries one lost response, removes only this occurrence and can restore after reload',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await enter(page);
  const form=await select(page);
  await form.getByLabel('调整方式').selectOption('cancel');
  await form.getByLabel('调整依据').fill('教师通知本次停课');
  let lose=true;
  await page.route('**/api/drafts/course-change',async route=>{
    if(!lose){await route.continue();return;}
    lose=false;const response=await route.fetch();expect(response.ok()).toBeTruthy();await route.abort();
  });
  await form.getByRole('button',{name:'预览课程调整'}).click();
  await expect(form.getByRole('alert')).toBeVisible();
  await form.getByRole('button',{name:'预览课程调整'}).click();
  const drafts=await(await page.request.get('/api/drafts')).json();
  expect(drafts.filter((d:any)=>d.data.draft_kind==='course_change')).toHaveLength(1);
  await save(page);
  await expect(page.locator('.fc-event').filter({hasText:'待调整高数'})).toHaveCount(0);
  const later=await(await page.request.get('/api/occurrences?start=2026-10-21&end=2026-10-21')).json();
  expect(later.filter((e:any)=>e.title==='待调整高数')).toHaveLength(1);
  await page.reload();await page.getByRole('button',{name:'课表',exact:true}).click();
  await expect(page.getByRole('region',{name:'已确认课程调整'})).toContainText('本次已停课');
  await page.getByRole('button',{name:'恢复原课（先预览）'}).click();await save(page);
  await expect(page.locator('.fc-event').filter({hasText:'待调整高数'})).toHaveCount(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  const exported=await(await page.request.get('/api/data-export')).json();
  expect(exported.resources.filter((r:any)=>r.kind==='planning_event'&&r.data.event_type==='course_exception_changed')).toHaveLength(2);
});
