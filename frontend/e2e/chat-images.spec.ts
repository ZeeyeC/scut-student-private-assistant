import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
const file=(name='homework')=>new URL('./fixtures/chat-images/'+name+'.png',import.meta.url);
async function enter(page:Page){
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`images-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');
 await page.getByRole('button',{name:'注册并登录'}).click();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();
 await expect(page.getByLabel('给助手的消息')).toBeVisible();
}
async function choose(page:Page,name='homework'){
 await page.getByRole('button',{name:'附件',exact:true}).click();
 await expect(page.getByRole('menuitem')).toHaveText(['图片识别作业','导入课表']);
 await page.getByLabel('选择作业截图').setInputFiles({name:name+'.png',mimeType:'image/png',buffer:readFileSync(file(name))});
 await page.keyboard.press('Escape');
 await expect(page.getByAltText('待发送的作业截图')).toBeVisible();
}
async function send(page:Page){
 await page.getByRole('checkbox',{name:'同意将图片及课程候选发送给配置的模型供应商'}).check();
 await page.getByRole('button',{name:'发送作业截图'}).click();
}
test('image-only chat identifies two items, corrects original, explicitly saves and replays image history',async({page})=>{
 await enter(page);let uploads=0;page.on('request',r=>{if(r.url().endsWith('/api/assets')&&r.method()==='POST')uploads++});
 await choose(page);expect(uploads).toBe(0);await expect(page.getByRole('button',{name:'发送作业截图'})).toBeDisabled();await send(page);
 const review=page.getByRole('complementary',{name:'草稿校对区'});
 await expect(review.getByRole('heading',{name:'核对原图和识别结果'})).toBeVisible();
 await expect.poll(()=>review.getByRole('textbox',{name:'标题',exact:true}).evaluateAll(nodes=>nodes.map(n=>(n as HTMLInputElement).value))).toEqual(['高数作业','英语作业']);
 expect(await page.request.get('/api/tasks').then(r=>r.json())).toEqual([]);
 await page.getByLabel('给助手的消息').fill('修改第二项为英语听力');await expect(page.locator('.composer-bottom button')).toBeEnabled();await page.getByLabel('给助手的消息').press('Enter');
 await expect.poll(()=>review.getByRole('textbox',{name:'标题',exact:true}).evaluateAll(nodes=>nodes.map(n=>(n as HTMLInputElement).value))).toEqual(['高数作业','英语听力']);
 await expect(review.getByAltText('待校对的作业原图')).toBeVisible();
 await review.getByRole('button',{name:'确认保存',exact:true}).click();
 await expect.poll(()=>page.request.get('/api/tasks').then(r=>r.json()).then(x=>x.length)).toBe(2);
 await page.reload();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();
 await expect(page.locator('.message.user img').first()).toBeVisible();expect(uploads).toBe(1);
});
test('drop and paste share preview validation, reject multiple files and preserve text paste',async({page})=>{
 await enter(page);let uploads=0;page.on('request',r=>{if(r.url().endsWith('/api/assets')&&r.method()==='POST')uploads++});
 const bytes=Array.from(readFileSync(file()));
 await page.evaluate(bytes=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(bytes)],'拖入.png',{type:'image/png'}));document.querySelector('[data-testid=chat-image-drop]')!.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}))},bytes);
 await expect(page.getByText('拖入.png',{exact:true})).toBeVisible();
 await page.evaluate(bytes=>{const dt=new DataTransfer();for(const name of ['一.png','二.png'])dt.items.add(new File([new Uint8Array(bytes)],name,{type:'image/png'}));document.querySelector('[data-testid=chat-image-drop]')!.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}))},bytes);
 await expect(page.getByRole('alert')).toContainText('每次添加一张');await expect(page.getByText('拖入.png',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'移除作业截图'}).click();
 await page.evaluate(bytes=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(bytes)],'粘贴.png',{type:'image/png'}));document.querySelector('textarea[aria-label="给助手的消息"]')!.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}))},bytes);
 await expect(page.getByText('粘贴.png',{exact:true})).toBeVisible();expect(uploads).toBe(0);
 const textPasteAllowed=await page.evaluate(()=>{const dt=new DataTransfer();dt.setData('text/plain','普通文字');const e=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});document.querySelector('textarea[aria-label="给助手的消息"]')!.dispatchEvent(e);return !e.defaultPrevented});
 expect(textPasteAllowed).toBe(true);
 await page.getByLabel('选择作业截图').setInputFiles({name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('text')});
 await expect(page.getByRole('alert')).toContainText('仅支持');await expect(page.getByText('粘贴.png',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'新会话',exact:true}).click();await expect(page.getByAltText('待发送的作业截图')).toHaveCount(0);
});
test('failed vision retries same run, cancelling vision leaves no actionable draft',async({page})=>{
 await enter(page);await choose(page,'retry');await send(page);
 await expect(page.getByRole('button',{name:'重试图片识别'})).toBeVisible();await page.getByRole('button',{name:'重试图片识别'}).click();
 await expect(page.getByRole('heading',{name:'核对原图和识别结果'})).toBeVisible();
 await page.getByRole('button',{name:'新会话',exact:true}).click();
 await expect(page.getByRole('heading',{name:'核对原图和识别结果'})).toHaveCount(0);
 await choose(page,'cancel');await send(page);await expect(page.getByRole('button',{name:'取消图片识别'})).toBeVisible();await page.getByRole('button',{name:'取消图片识别'}).click();
 await expect(page.getByText('已取消识别',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'核对原图和识别结果'})).toHaveCount(0);
});
