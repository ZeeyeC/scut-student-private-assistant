import {test,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {visualFixture} from './ui-visual-fixture';
const output=fileURLToPath(new URL('../../docs/validation/demo2.9/visual/',import.meta.url));

test('workspace matches the accepted reference geometry on every page',async({page})=>{
 page.on('pageerror',error=>console.log('Visual fixture runtime:',error.message));
 await mkdir(output,{recursive:true});await page.setViewportSize({width:1280,height:782});const fixture=await visualFixture(page,{taskCount:5});await page.goto('/');
 await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
 const geometry:Record<string,unknown>={};
 for(const [id,label] of [['today','今日'],['calendar','日程'],['tasks','任务'],['assistant','助手'],['settings','设置']]){
  if(id==='tasks'){fixture.setTaskCount(9);await page.reload();}
  await page.getByRole('button',{name:label,exact:true}).click();
  await expect(page.getByRole('heading',{name:label,exact:true})).toBeVisible();
  if(id==='today'){await expect(page.locator('.next-task h2')).toHaveText('高数 · 第三章习题');await expect(page.locator('.summary-task-row')).toHaveCount(3);}
  if(id==='calendar'){await expect(page.locator('.fc-v-event')).toHaveCount(10);await expect(page.getByText('正在读取日程…',{exact:true})).toBeHidden();}
  if(id==='tasks')await expect(page.getByText('待估时',{exact:true})).toHaveCount(0);
  if(id==='assistant')await expect(page.locator('.message.assistant')).toContainText('下午先完成');
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
  await page.mouse.move(1279,781);await page.screenshot({path:output+id+'-desktop.png'});
  geometry[id]=await page.locator('.page-head').first().boundingBox();
  if(id==='calendar'){await page.getByRole('button',{name:'导入课表',exact:true}).click();await expect(page.getByRole('heading',{name:'从学校导入',exact:true})).toBeVisible();await expect(page.getByLabel('课表导入浏览器')).toHaveValue('chrome');await expect(page.getByLabel('课表导入浏览器')).toBeEnabled();await writeFile(output+'import-metrics.json',JSON.stringify(await page.locator('.detail-panel:visible').evaluate(el=>{const origin=el.getBoundingClientRect();return [...el.querySelectorAll('header,.import-school-primary,.import-school-heading,.import-school-heading svg,.import-school-primary>p,.import-other-heading,.timetable-import-method,.import-extension-guide')].map(e=>{const r=e.getBoundingClientRect(),c=getComputedStyle(e);return[e.className?.baseVal??e.className,{x:r.x-origin.x,y:r.y-origin.y,w:r.width,h:r.height,font:c.font,margin:c.margin,padding:c.padding}];});}),null,2));await page.mouse.move(1279,781);await page.screenshot({path:output+'import-default.png'});await page.getByRole('button',{name:'关闭导入课表',exact:true}).click();}
  if(id==='assistant'||id==='calendar'){const selectors=id==='assistant'?['.chat-toolbar','.assistant-layout','.chat.card','.composer','.composer textarea','.composer-bottom']:['.calendar-toolbar','.workspace-calendar','.fc-col-header','.fc-timegrid-body','.fc-event-main'];const metrics=await page.evaluate(selectors=>Object.fromEntries(selectors.map(selector=>{const el=document.querySelector(selector)!;const r=el.getBoundingClientRect(),c=getComputedStyle(el);return [selector,{rect:{x:r.x,y:r.y,width:r.width,height:r.height},font:c.font,padding:c.padding,margin:c.margin}];})),selectors);await writeFile(output+id+'-metrics.json',JSON.stringify(metrics,null,2));}
  if(id==='tasks'){await page.getByRole('button',{name:'高数 · 第三章习题',exact:true}).click();await expect(page.locator('.task-detail-step')).toHaveCount(1);await page.mouse.move(1279,781);await page.screenshot({path:output+'task-detail.png'});await page.getByRole('button',{name:'关闭高数 · 第三章习题',exact:true}).click();}
 }
 await writeFile(output+'geometry.json',JSON.stringify(geometry,null,2));
 expect((geometry.today as {y:number}).y).toBeCloseTo(31,0);
});

test('agenda marker never overlaps titles or secondary text when text grows',async({page})=>{
 await visualFixture(page,{longTitle:true,taskCount:5});await page.goto('/');
 await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
 await expect(page.locator('.agenda-marker')).toHaveCount(4);
 for(const width of [1280,1024,960,768,560,390,320])for(const scale of [1,1.25,2]){
  await page.setViewportSize({width,height:900});
  await page.locator('.today-agenda-row').evaluateAll((rows,scale)=>rows.forEach(row=>row.querySelectorAll('strong,small').forEach(el=>(el as HTMLElement).style.fontSize=`${(el.tagName==='STRONG'?13:11)*scale}px`)),scale);
  const gaps=await page.locator('.today-agenda-row').evaluateAll(rows=>rows.map(row=>{
   const marker=row.querySelector('.agenda-marker')!.getBoundingClientRect();
   return [...row.querySelectorAll('strong,small')].map(text=>text.getBoundingClientRect().left-marker.right);
  }).flat());
  expect(Math.min(...gaps)).toBeGreaterThanOrEqual(11.9);
  expect(await page.locator('#workspace-content').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 }
});

test('long task details keep their footer and left navigation inside narrow windows',async({page})=>{
 await visualFixture(page,{longTitle:true});await page.goto('/');
 await page.getByRole('button',{name:'任务',exact:true}).click();
 await page.locator('.summary-task-title').first().click();
 const panel=page.locator('.detail-panel:visible');
 for(const width of [1280,560,390,320]){
  await page.setViewportSize({width,height:782});
  const bounds=await panel.boundingBox(),sidebar=await page.locator('.workspace-sidebar').boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(sidebar!.width);
  expect(await panel.locator('.detail-panel-content').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  await panel.locator('.detail-panel-content').evaluate(el=>el.scrollTop=el.scrollHeight);
  await expect(panel.getByRole('button',{name:'标记完成',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.scrollingElement?.scrollTop)).toBe(0);
 }
 await panel.getByRole('button',{name:'关闭',exact:true}).click();
 await expect(page.getByRole('button',{name:'新建任务',exact:true})).toBeEnabled();
});
