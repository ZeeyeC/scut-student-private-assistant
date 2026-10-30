import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
const require=createRequire(new URL('../../../frontend/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const out=new URL('./screens/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:980},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:5349/');await page.getByRole('heading',{name:'今日',exact:true}).waitFor();
const results=[];
for(const [view,name] of [['today','今日'],['calendar','日程'],['tasks','任务'],['assistant','助手'],['settings','设置']]){
 await page.locator(`.primary-nav [data-nav="${view}"]`).count()?await page.locator(`.primary-nav [data-nav="${view}"]`).click():await page.locator(`.sidebar-bottom [data-nav="${view}"]`).click();
 await page.getByRole('heading',{name,exact:true}).waitFor();
 await page.screenshot({path:new URL(`${view}-desktop.png`,out).pathname});results.push(view+' desktop rendered');
}
await page.locator('[data-nav="today"]').first().click();
await page.getByRole('button',{name:'安排今天',exact:true}).click();await page.getByRole('button',{name:'预览安排',exact:true}).click();
await page.getByRole('heading',{name:'确认安排',exact:true}).waitFor();await page.screenshot({path:new URL('plan-review.png',out).pathname});
await page.getByRole('button',{name:'确认安排',exact:true}).click();
if(await page.getByRole('dialog').count()&&await page.getByRole('dialog').isVisible())throw Error('plan confirmation did not close');results.push('plan preview and explicit confirmation');
await page.getByRole('button',{name:'高数 · 第三章习题',exact:true}).click();await page.getByRole('heading',{name:'任务详情',exact:true}).waitFor();
await page.screenshot({path:new URL('task-detail.png',out).pathname});await page.getByRole('button',{name:'关闭面板',exact:true}).click();
await page.getByRole('button',{name:'开始专注',exact:true}).click();await page.getByRole('button',{name:'结束',exact:true}).click();
await page.getByRole('heading',{name:'记录本次学习',exact:true}).waitFor();await page.getByRole('button',{name:'保存记录',exact:true}).click();results.push('focus and execution drawer');
await page.locator('.primary-nav [data-nav="tasks"]').click();await page.getByRole('button',{name:'新建任务',exact:true}).click();
await page.getByLabel('任务名称',{exact:true}).fill('原型检查任务');await page.getByRole('button',{name:'添加任务',exact:true}).last().click();
await page.getByRole('button',{name:'原型检查任务',exact:true}).waitFor();results.push('create task in prototype memory');
await page.getByRole('tab',{name:'目标',exact:true}).click();await page.screenshot({path:new URL('goals-desktop.png',out).pathname});
await page.getByRole('tab',{name:'复盘',exact:true}).click();await page.screenshot({path:new URL('review-desktop.png',out).pathname});
await page.locator('.primary-nav [data-nav="calendar"]').click();await page.getByRole('button',{name:'导入课表',exact:true}).click();
await page.getByRole('button',{name:'使用示例预览',exact:true}).click();await page.getByRole('heading',{name:'校对课表',exact:true}).waitFor();
await page.getByRole('button',{name:'确认导入',exact:true}).click();results.push('timetable import preview');
await page.reload();await page.getByRole('button',{name:'紧凑窗口',exact:true}).click();await page.locator('.primary-nav [data-nav="today"]').click();
await page.screenshot({path:new URL('today-compact.png',out).pathname});
await page.locator('.primary-nav [data-nav="calendar"]').click();await page.screenshot({path:new URL('calendar-compact.png',out).pathname});
for(const width of [390,320]){
 await page.setViewportSize({width,height:880});
 for(const view of ['today','calendar','tasks','assistant','settings']){
  await page.evaluate(view=>document.querySelector(`[data-nav="${view}"]`).click(),view);
  const overflow=await page.evaluate(()=>({outer:document.documentElement.scrollWidth>innerWidth,main:document.querySelector('main').scrollWidth>document.querySelector('main').clientWidth+1}));
  if(overflow.outer||overflow.main)throw Error(`${view} overflows at ${width}: ${JSON.stringify(overflow)}`);
 }
 results.push(`${width}px all views fit`);
}
if(errors.length)throw Error(errors.join('\n'));
await writeFile(new URL('./preview-verification.json',import.meta.url),JSON.stringify({passed:true,scope:'static design prototype only, sample data, no product backend',results,console_errors:errors},null,2)+'\n');
console.log(JSON.stringify({passed:true,checks:results.length,results}));await browser.close();
