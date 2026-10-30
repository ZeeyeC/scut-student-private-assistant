import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

async function seed(page:Page){
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await page.goto('/');
  await page.getByRole('button',{name:'创建账号',exact:true}).click();
  await page.getByLabel('邮箱').fill(`semester-${crypto.randomUUID()}@example.com`);
  await page.getByLabel('密码').fill('Student!Password2026');
  await page.getByRole('button',{name:'注册并登录'}).click();
  await expect(page.getByRole('heading',{name:'今天，专注几件事。'})).toBeVisible();
  await page.evaluate(async()=>{
    const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
    const write=async(path:string,body:unknown,method='POST')=>{
      const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
      if(!r.ok)throw new Error(await r.text());return r.json();
    };
    const pref=await(await fetch('/api/after-class/preferences')).json();
    await write('/after-class/preferences',{revision:pref.revision,enabled:false},'PUT');
    const s=await(await fetch('/api/settings')).json();
    s.data={...s.data,week1_monday:'2026-10-12',week_count:4,periods:{'1':{start:'09:00',end:'10:00'},'3':{start:'14:00',end:'15:00'}}};
    await write('/settings',s,'PUT');
    const d=await write('/drafts/timetable',{semester_label:'合成校历用例',courses:[
      {source_key:'math',name:'校历分段高数',weekday:3,weeks:[1,2,3],periods:[1,3],location:'101',campus:'主校区'},
      {source_key:'physics',name:'校历物理',weekday:3,weeks:[1,2,3],periods:[1],location:'102',campus:'主校区'},
    ]});await write(`/drafts/${d.id}/confirm`,{revision:d.revision});
  });
  await page.getByRole('button',{name:'课表',exact:true}).click();
  return page.getByRole('region',{name:'学期校历与批量调课',exact:true});
}
async function prepareRule(page:Page,kind:string){
  const section=await seed(page);
  await section.getByLabel('规则类型').selectOption(kind);
  await section.getByLabel('通知名称').fill('合成第二周学校通知');
  await section.getByLabel('规则依据',{exact:true}).fill('合成教务通知第3条');
  await section.getByLabel('通知作用范围').fill('仅所选课程与明确原课日期，不包含其他课程');
  return section;
}
async function confirm(page:Page){
  const review=page.getByRole('region',{name:'校历批量调整草稿',exact:true});
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await expect(review.getByRole('button',{name:'确认保存',exact:true})).toBeVisible();
  const ack=review.getByRole('checkbox');
  if(await ack.count())await ack.check();
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
}

test('practice range previews four actual classes then atomically saves and restores original exceptions',async({page})=>{
  const section=await prepareRule(page,'practice_week');
  await section.getByLabel('校历分段高数',{exact:false}).check();
  await section.getByLabel('校历物理',{exact:false}).check();
  await section.getByLabel('原课开始日期').fill('2026-10-12');
  await section.getByLabel('原课结束日期（包含）').fill('2026-10-25');
  await section.getByRole('button',{name:'预览批量调整',exact:true}).click();
  const review=page.getByRole('region',{name:'校历批量调整草稿',exact:true});
  await expect(review).toContainText('共 4 次课程');
  await review.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.4.9/semester-batch-preview.png',import.meta.url))});
  expect(await(await page.request.get('/api/course-changes')).json()).toHaveLength(0);
  await confirm(page);
  await expect.poll(async()=> (await(await page.request.get('/api/course-changes')).json()).length).toBe(4);
  await page.reload();await page.getByRole('button',{name:'课表',exact:true}).click();
  await page.getByRole('button',{name:'撤销整批（先预览）',exact:true}).click();
  await expect(page.getByRole('region',{name:'校历批量调整草稿',exact:true})).toContainText('恢复本批次之前的课程例外');
  await confirm(page);
  expect(await(await page.request.get('/api/course-changes')).json()).toHaveLength(0);
  await expect(page.getByRole('region',{name:'校历批次历史'})).toContainText('已撤销，原调整记录保留');
});

test('mobile makeup requires explicit mapping and keeps nonconsecutive periods after save',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const section=await prepareRule(page,'makeup');
  await section.getByLabel('校历分段高数',{exact:false}).check();
  await section.getByLabel('调整方式').selectOption('move');
  await section.getByRole('button',{name:'预览批量调整',exact:true}).click();
  await expect(section.getByRole('alert')).toContainText('日期映射');
  await section.getByRole('button',{name:'添加日期映射'}).click();
  await section.getByLabel('原课日期 1',{exact:true}).fill('2026-10-14');
  await section.getByLabel('目标补课日期 1',{exact:true}).fill('2026-10-18');
  await section.getByRole('button',{name:'预览批量调整',exact:true}).click();
  const review=page.getByRole('region',{name:'校历批量调整草稿',exact:true});
  await expect(review).toContainText('保留 2 段授课');
  await review.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.4.9/makeup-mobile-preview.png',import.meta.url))});
  await confirm(page);
  const occurrences=await(await page.request.get('/api/occurrences?start=2026-10-18&end=2026-10-18')).json();
  expect(occurrences).toHaveLength(1);
  expect(occurrences[0].occupied_intervals.map((i:any)=>[i.starts_at.slice(11,16),i.ends_at.slice(11,16)])).toEqual([['09:00','10:00'],['14:00','15:00']]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
