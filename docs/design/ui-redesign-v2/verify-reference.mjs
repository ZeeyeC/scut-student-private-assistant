import {chromium} from '../../../frontend/node_modules/playwright/index.mjs';
import {fileURLToPath} from 'node:url';
import {writeFile} from 'node:fs/promises';
const directory=fileURLToPath(new URL('.',import.meta.url));
const updateReference=process.argv.includes('--update-reference');
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1312,height:1000},deviceScaleFactor:1});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
try{
 await page.goto(new URL('index.html',import.meta.url).href);
 const frame=page.frameLocator('iframe');
 const app=frame.locator('.cr-window');
 await frame.locator('.cr-next').waitFor();
 const agendaGaps=await frame.locator('.cr-agenda-entry').evaluateAll(entries=>entries.map(el=>{
  const marker=getComputedStyle(el,'::before'),edge=el.getBoundingClientRect().left+(parseFloat(marker.left)||0)+parseFloat(marker.width);
  return [...el.querySelectorAll('strong,small')].map(text=>text.getBoundingClientRect().left-edge);
 }).flat());
 if(agendaGaps.some(gap=>gap<11.9))throw Error('F09: agenda marker overlaps text or lacks 12px spacing: '+JSON.stringify(agendaGaps));
 const metrics=await app.evaluate(el=>({window:{width:el.clientWidth,height:el.clientHeight},productContent:{width:el.querySelector('.cr-main').getBoundingClientRect().right-el.querySelector('.cr-sidebar').getBoundingClientRect().left,height:el.querySelector('.cr-main').clientHeight},sidebar:el.querySelector('.cr-sidebar').getBoundingClientRect().width,mainPadding:getComputedStyle(el.querySelector('.cr-main')).padding,bodyScroll:document.scrollingElement.scrollTop}));
 if(metrics.productContent.width!==1280||metrics.productContent.height!==782)throw Error('Canonical product area is not 1280 × 782');
 if(updateReference)await app.screenshot({path:directory+'screens/today-desktop.png'});
 await frame.locator('[data-page=calendar]').click();
 if(updateReference)await app.screenshot({path:directory+'screens/calendar-desktop.png'});
 await frame.getByRole('button',{name:'导入课表',exact:true}).click();
 const browserPrimary=frame.locator('.cr-browser-primary');
 if(!await browserPrimary.isVisible())throw Error('Browser import is not the primary default');
 if(await frame.locator('[data-image-import]').isVisible()||await frame.locator('[data-text-import]').isVisible())throw Error('Secondary import forms expanded by default');
 if(updateReference)await app.screenshot({path:directory+'screens/import-default.png'});
 await frame.locator('[data-action=browser-import]').click();
 if(!await frame.locator('[data-import-status]').isVisible())throw Error('Local import demo did not advance');
 await frame.getByRole('button',{name:'查看示例回传',exact:true}).click();
 if(await frame.locator('[data-drawer-title]').textContent()!=='校对课表')throw Error('Import preview not shown');
 await frame.getByRole('button',{name:'关闭详情',exact:true}).click();
 await frame.locator('[data-page=tasks]').click();
 const sidebarBefore=await frame.locator('.cr-sidebar').boundingBox();
 await frame.locator('.cr-main').evaluate(el=>el.scrollTop=500);
 const scroll=await frame.locator('.cr-main').evaluate(el=>el.scrollTop);
 const sidebarAfter=await frame.locator('.cr-sidebar').boundingBox();
 if(scroll<50||Math.abs(sidebarBefore.y-sidebarAfter.y)>.5||Math.abs(sidebarBefore.height-sidebarAfter.height)>.5)throw Error('Sidebar moved with long content');
 await frame.locator('.cr-main').evaluate(el=>el.scrollTop=0);
 if(updateReference)await app.screenshot({path:directory+'screens/tasks-desktop.png'});
 await frame.locator('[data-task=math]').click();
 if(updateReference)await app.screenshot({path:directory+'screens/task-detail.png'});
 await frame.getByRole('button',{name:'关闭详情',exact:true}).click();
 for(const p of ['assistant','settings']){await frame.locator(`[data-page=${p}]`).click();if(updateReference)await app.screenshot({path:directory+`screens/${p}-desktop.png`});}
 await frame.getByRole('tab',{name:'桌宠待办'}).click();
 if(await frame.locator('.cr-pet-panel').isVisible())throw Error('Pet panel visible without click');
 if(updateReference)await frame.locator('.cr-desktop').screenshot({path:directory+'screens/pet-idle.png'});
 await frame.locator('[data-action=pet-toggle]').click();
 const petGeometry=await frame.locator('.cr-pet-composition').evaluate(el=>{const image=el.querySelector('img').getBoundingClientRect(),panel=el.querySelector('.cr-pet-panel').getBoundingClientRect();return {panel:{width:panel.width,height:panel.height},visibleGap:image.x+104/420*image.width-panel.right,sourceAlphaBounds:[104,37,372,541],sourceSize:[420,560]};});
 if(Math.abs(petGeometry.visibleGap-32)>1||petGeometry.panel.width!==328||petGeometry.panel.height!==360)throw Error('Pet optical geometry does not match contract');
 if(updateReference)await frame.locator('.cr-desktop').screenshot({path:directory+'screens/pet-todos.png'});
 await frame.locator('[data-pet-task=math]').click();
 if(updateReference)await frame.locator('.cr-desktop').screenshot({path:directory+'screens/pet-detail.png'});
 await frame.locator('[data-action=pet-all]').click();
 if(!await frame.locator('.cr-window').isVisible()||await frame.locator('[data-drawer-title]').textContent()!=='任务详情')throw Error('Pet task did not open exact App task detail');
 await frame.getByRole('button',{name:'关闭详情',exact:true}).click();
 const overflow=[];
 for(const width of [1280,1024,960,768,560,390,320]){
  await page.setViewportSize({width,height:1000});
  for(const p of ['today','calendar','tasks','assistant','settings']){
   await frame.locator(`[data-page=${p}]`).click();
   const size=await frame.locator('#campus-ui-revision').evaluate(el=>({width:el.clientWidth,scrollWidth:el.scrollWidth,mainWidth:el.querySelector('.cr-main').clientWidth,mainScrollWidth:el.querySelector('.cr-main').scrollWidth}));
   if(size.scrollWidth>size.width+1||size.mainScrollWidth>size.mainWidth+1)overflow.push({width,page:p,...size});
  }
  await frame.locator('[data-page=calendar]').click();await frame.getByRole('button',{name:'导入课表',exact:true}).click();
  const importOverflow=await frame.locator('.cr-drawer-body').evaluate(el=>el.scrollWidth>el.clientWidth+1);
  if(importOverflow)overflow.push({width,page:'import'});
  if(width===390)if(updateReference)await app.screenshot({path:directory+'screens/import-compact.png'});
  await frame.getByRole('button',{name:'关闭详情',exact:true}).click();
  await frame.getByRole('tab',{name:'桌宠待办'}).click();await frame.locator('[data-action=pet-toggle]').click();
  const petSize=await frame.locator('.cr-desktop').evaluate(el=>({width:el.clientWidth,scrollWidth:el.scrollWidth}));
  if(petSize.scrollWidth>petSize.width+1)overflow.push({width,page:'pet',...petSize});
  await frame.locator('[data-action=pet-close]').click();await frame.getByRole('tab',{name:'完整窗口'}).click();
 }
 await page.setViewportSize({width:1280,height:1000});await frame.locator('[data-page=today]').click();
 await page.emulateMedia({colorScheme:'dark'});if(updateReference)await app.screenshot({path:directory+'screens/today-dark.png'});
 const result={kind:'design-prototype-only',productImplementation:false,fixture:'synthetic',errors,overflow,widths:[1280,1024,960,768,560,390,320],agendaMarkerTextGaps:agendaGaps,metrics,petGeometry,sidebarScroll:{scrollTop:scroll,before:sidebarBefore,after:sidebarAfter},checks:['five pages','browser import primary; two secondary methods collapsed','local import preview','sidebar stationary during content scroll','pet closed by default; click toggles','pet selected task opens exact App detail','responsive overflow','dark appearance','F09: marker to title and secondary text gap at least 12px']};
 if(updateReference)await writeFile(directory+'preview-verification.json',JSON.stringify(result,null,2)+'\n');
 if(errors.length||overflow.length)throw Error(JSON.stringify({errors,overflow}));
 process.stdout.write(JSON.stringify(result)+'\n');
}finally{await browser.close();}
