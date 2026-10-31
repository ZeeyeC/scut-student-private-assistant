import {test,expect,type Page} from '@playwright/test';
async function enter(page:Page){
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`memory-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');
 await page.getByRole('button',{name:'注册并登录'}).click();await nav(page,'助手');
}
async function nav(page:Page,name:string){if(await page.getByRole('dialog').count())await page.keyboard.press('Escape');await (name==='设置'?page.getByRole('button',{name,exact:true}):page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name,exact:true})).click();}
async function send(page:Page,text:string){await page.getByLabel('给助手的消息').fill(text);await page.getByRole('button',{name:'发送',exact:true}).click();}
async function memorySettings(page:Page){await nav(page,'设置');await page.getByRole('button',{name:'学习偏好',exact:true}).click();return page.getByRole('region',{name:'记忆与偏好'});}
test('chat proposes, human confirms, new chat recalls, forget isolates both old chats',async({page})=>{
 await enter(page);await send(page,'记住以后回答简短些');
 const panel=page.getByRole('complementary',{name:'草稿校对区'});
 await expect(panel.getByRole('button',{name:'确认记忆',exact:true})).toBeVisible();
 expect((await page.request.get('/api/memories').then(r=>r.json())).memories).toEqual([]);
 await expect(page.locator('.message.assistant').last()).toContainText('已提出记忆候选');
 await expect.poll(()=>page.request.get('/api/agent/threads').then(r=>r.json()).then(async ts=>Promise.all(ts.map((t:any)=>page.request.get(`/api/agent/threads/${t.id}/runs`).then(r=>r.json())))).then(groups=>groups.flat().every((r:any)=>r.data.status==='done'))).toBe(true);
 await panel.getByRole('button',{name:'确认记忆',exact:true}).click();
 await expect(panel.getByRole('button',{name:'确认记忆',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'新会话',exact:true}).click();await send(page,'我有什么偏好');
 await expect(page.locator('.message.assistant').last()).toContainText('你希望回答简短些');
 const manager=await memorySettings(page);
 await expect(manager.getByText('以后回答简短些',{exact:true})).toBeVisible();
 await manager.getByRole('button',{name:'遗忘',exact:true}).click();
 await expect(manager.getByRole('button',{name:'确认遗忘'})).toBeVisible();
 await manager.getByRole('button',{name:'确认遗忘'}).click();
 await expect(manager.getByText('还没有已确认记忆。')).toBeVisible();
 await nav(page,'助手');await send(page,'我有什么偏好');
 await expect(page.locator('.message.assistant').last()).toContainText('没有可召回的偏好');
 await page.reload();await nav(page,'助手');await page.getByRole('button',{name:'新会话',exact:true}).click();await send(page,'我有什么偏好');
 await expect(page.locator('.message.assistant').last()).toContainText('没有可召回的偏好');
});
test('settings review edits numeric profile, rejects, disables recall and clears explicitly',async({page})=>{
 await enter(page);const m=await memorySettings(page);
 await m.getByRole('button',{name:'添加记忆',exact:true}).click();
 await m.getByLabel('内容',{exact:true}).fill('一次专注25分钟');
 await m.getByLabel('同步永久学习偏好').selectOption('focus_minutes');
 await m.getByLabel('时长（分钟）').fill('25');
 await m.getByRole('button',{name:'提出记忆候选'}).click();
 await m.getByRole('button',{name:'确认记忆',exact:true}).click();
 await expect.poll(()=>page.request.get('/api/profile').then(r=>r.json()).then(x=>x.data.preferences.focus_minutes)).toBe(25);
 await m.getByRole('button',{name:'修改',exact:true}).click();await m.getByLabel('时长（分钟）').fill('35');
 await m.getByRole('button',{name:'提出记忆候选'}).click();
 await m.getByRole('button',{name:'拒绝',exact:true}).click();
 expect((await page.request.get('/api/profile').then(r=>r.json())).data.preferences.focus_minutes).toBe(25);
 await m.getByRole('checkbox',{name:'使用已确认记忆'}).uncheck();
 await expect.poll(()=>page.request.get('/api/memories').then(r=>r.json()).then(x=>x.settings.data.recall_enabled)).toBe(false);
 page.once('dialog',d=>d.accept());await m.getByRole('button',{name:'清空记忆'}).click();
 await expect(m.getByText('还没有已确认记忆。')).toBeVisible();
 expect((await page.request.get('/api/profile').then(r=>r.json())).data.preferences.focus_minutes).toBe(null);
});
test('secret rejection preserves form, candidate text cannot execute markup',async({page})=>{
 await enter(page);const m=await memorySettings(page);await m.getByRole('button',{name:'添加记忆',exact:true}).click();
 await m.getByLabel('记忆主题').fill('reply');await m.getByLabel('内容',{exact:true}).fill('api_key=synthetic-rejected');
 await m.getByRole('button',{name:'提出记忆候选'}).click();await expect(m.getByRole('alert')).toContainText('记忆不能包含');
 await expect(m.getByLabel('内容',{exact:true})).toHaveValue('api_key=synthetic-rejected');
 await m.getByLabel('内容',{exact:true}).fill('<img src=x onerror="window.memoryInjected=true">');
 await m.getByRole('button',{name:'提出记忆候选'}).click();
 await expect(m.getByText('新内容：<img src=x onerror="window.memoryInjected=true">',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>Boolean((window as any).memoryInjected))).toBe(false);
});
