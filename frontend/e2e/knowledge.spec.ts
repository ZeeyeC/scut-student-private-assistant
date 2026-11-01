import {test,expect,type Page} from '@playwright/test';
async function enter(page:Page){
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`knowledge-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');
 await page.getByRole('button',{name:'注册并登录'}).click();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();
}
test('documents stay local before send, source tools answer with citations, retained across chats',async({page})=>{
 await enter(page);let uploads=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/api/knowledge/documents'))uploads++});
 await page.getByRole('button',{name:'附件',exact:true}).click();await expect(page.getByRole('menuitem',{name:'课程资料',exact:true})).toBeVisible();
 await page.getByLabel('选择课程资料',{exact:true}).setInputFiles({name:'课程讲义.md',mimeType:'text/markdown',buffer:Buffer.from('本章作业：完成微积分习题1至3题。')});await page.keyboard.press('Escape');
 await expect(page.getByText('课程讲义.md',{exact:true})).toBeVisible();expect(uploads).toBe(0);
 await page.getByLabel('给助手的消息').fill('资料里的作业是什么');await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect(page.locator('.message.assistant').last()).toContainText('微积分');await expect(page.locator('.message.assistant').last()).toContainText('段落1');
 expect(uploads).toBe(1);expect((await page.request.get('/api/tasks')).ok()).toBe(true);expect(await page.request.get('/api/tasks').then(r=>r.json())).toEqual([]);
 await page.getByRole('button',{name:'新会话',exact:true}).click();await page.getByRole('button',{name:'课程资料',exact:true}).click();
 const panel=page.getByRole('dialog',{name:'课程资料',exact:true});await expect(panel.getByText('课程讲义.md',{exact:true})).toBeVisible();
 await panel.getByRole('button',{name:'选用',exact:true}).click();await page.keyboard.press('Escape');await expect(page.getByLabel('已选课程资料')).toContainText('课程讲义.md');
 await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.locator('.message.assistant').last()).toContainText('微积分');expect(uploads).toBe(1);
});
test('settings show truthful optional semantic/search status, no automatic model download',async({page})=>{
 await enter(page);let prepares=0;page.on('request',r=>{if(r.url().endsWith('/semantic/prepare'))prepares++});
 await page.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('button',{name:'模型连接',exact:true}).click();
 await expect(page.getByText('未就绪（当前回退为关键词检索）',{exact:false})).toBeVisible();expect(prepares).toBe(0);
 await page.getByLabel('检索服务端点（URL）').fill('http://127.0.0.1:8888');await page.getByRole('button',{name:'保存检索地址'}).click();
 await expect(page.getByText('外部检索地址已更新')).toBeVisible();
 await page.getByLabel('检索服务端点（URL）').fill('');await page.getByRole('button',{name:'保存检索地址'}).click();await expect.poll(()=>page.request.get('/api/integrations').then(r=>r.json()).then(r=>r.search.configured)).toBe(false);
});

test('lost response for a reused source recovers the exact new operation',async({page})=>{
 await enter(page);
 await page.getByLabel('选择课程资料',{exact:true}).setInputFiles({name:'复习.md',mimeType:'text/markdown',buffer:Buffer.from('作业：完成微积分练习。')});
 await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.locator('.message.assistant')).toHaveCount(1);
 await expect.poll(()=>page.request.get('/api/agent/threads').then(r=>r.json()).then(async ts=>{const rs=await page.request.get(`/api/agent/threads/${ts.at(-1).id}/runs`).then(r=>r.json());return rs.every((r:any)=>r.data.status==='done');})).toBe(true);
 await page.getByRole('button',{name:'课程资料',exact:true}).click();await page.getByRole('dialog',{name:'课程资料',exact:true}).getByRole('button',{name:'选用',exact:true}).click();await page.keyboard.press('Escape');
 let lost=false;
 await page.route('**/api/agent/runs',async route=>{if(!lost){lost=true;await route.fetch();await route.abort('failed');}else await route.continue();});
 await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.locator('.message.assistant')).toHaveCount(2);await expect(page.locator('.message.assistant').last()).toContainText('微积分');
 const ts=await page.request.get('/api/agent/threads').then(r=>r.json());const rs=await page.request.get(`/api/agent/threads/${ts.at(-1).id}/runs`).then(r=>r.json());expect(rs).toHaveLength(2);
});
