import {chromium} from '../../../frontend/node_modules/playwright/index.mjs';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('.',import.meta.url));await mkdir(root+'screens',{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1280,height:1000},deviceScaleFactor:1,colorScheme:'light'});
try{
 await page.goto(new URL('existing-pages-reference.html',import.meta.url).href);await page.locator('.cr-next').waitFor();const app=page.locator('.cr-window');
 for(const [id,name] of [['today','今日'],['calendar','日程'],['tasks','任务'],['assistant','助手'],['settings','设置']]){
  await page.locator(`[data-page=${id}]`).click();await app.screenshot({path:root+`screens/${id}-desktop.png`});
  if(id==='calendar'){await page.getByRole('button',{name:'导入课表',exact:true}).click();await app.screenshot({path:root+'screens/import-default.png'});await page.getByRole('button',{name:'关闭详情',exact:true}).click();}
  if(id==='tasks'){await page.locator('[data-task=math]').click();await app.screenshot({path:root+'screens/task-detail.png'});await page.getByRole('button',{name:'关闭详情',exact:true}).click();}
 }
 // Approved knowledge prototype, never a product capture.
 await page.goto(new URL('reference-preview.html',import.meta.url).href);const frame=page.frameLocator('iframe');await frame.locator('#cp-files .cp-file').first().waitFor();
 await page.locator('iframe').evaluate(e=>{e.style.width='1280px';e.style.height='782px';});
 await frame.locator('.cp-window').evaluate(e=>{e.style.height='782px';e.style.border='0';e.style.borderRadius='0';});
 await frame.locator('.cp-window').screenshot({path:root+'screens/knowledge-desktop.png'});
 console.log(JSON.stringify({passed:true,source:'accepted design prototypes only; no product screenshots used'}));
}finally{await browser.close();}
