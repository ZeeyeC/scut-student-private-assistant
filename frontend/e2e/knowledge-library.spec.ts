import {test,expect,type Page} from '@playwright/test';

async function enter(page:Page){
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`library-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');
 await page.getByRole('button',{name:'注册并登录'}).click();await expect(page.getByRole('navigation',{name:'主导航'})).toBeVisible();
}
async function seed(page:Page){
 return page.evaluate(async()=>{
  const csrf=(await(await fetch('/api/csrf')).json()).csrf_token;
  const write=async(path:string,body:any)=>{const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());return r.json();};
  const d=await write('/drafts/timetable',{semester_label:'合成学期',courses:[{source_key:'math',name:'高等数学',weekday:1,weeks:[1,2],periods:[1],location:'A101'},{source_key:'physics',name:'大学物理',weekday:2,weeks:[1,2],periods:[1],location:'A102'}]});
  await write('/drafts/'+d.id+'/confirm',{revision:d.revision});
  const courses=await(await fetch('/api/courses')).json();
  for(const name of ['微积分讲义.md','课堂笔记.txt']){
   const form=new FormData();form.append('file',new File(['本章作业：完成微积分练习。'],name,{type:'text/plain'}));
   const r=await fetch('/api/knowledge/documents',{method:'POST',headers:{'X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:form});if(!r.ok)throw Error(await r.text());
  }
  return courses;
 });
}

test('standalone library preserves all files, groups the sidebar and reclassifies a real source',async({page})=>{
 await enter(page);const courses=await seed(page);const math=courses.find((c:any)=>c.data.name==='高等数学');
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();
 await expect(page.getByRole('heading',{name:'课程资料',exact:true})).toBeVisible();await expect(page.locator('.kb-file')).toHaveCount(2);
 const assistant=await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).boundingBox();const today=await page.getByRole('button',{name:'今日',exact:true}).boundingBox();expect(today!.y-assistant!.y-assistant!.height).toBeGreaterThanOrEqual(39);
 await page.getByRole('button',{name:'查看 微积分讲义.md',exact:true}).click();const detail=page.getByRole('dialog',{name:'文件详情',exact:true});
 await expect(detail).toContainText('段落1');await detail.getByLabel('所属课程',{exact:true}).selectOption(math.id);await detail.getByRole('button',{name:'保存分类',exact:true}).click();await expect(detail).toContainText('分类已更新');
 await detail.getByRole('button',{name:'关闭文件详情',exact:true}).click();await page.getByRole('button',{name:'高等数学 1',exact:true}).click();await expect(page.locator('.kb-file')).toHaveCount(1);
 await page.reload();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();await expect(page.locator('.kb-file')).toHaveCount(2);
});

test('using a saved file opens assistant with an attachment and never sends automatically',async({page})=>{
 await enter(page);await seed(page);let runs=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/agent/runs'))runs++});
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();await page.getByRole('button',{name:'查看 微积分讲义.md',exact:true}).click();
 await page.getByRole('button',{name:'用这份资料提问',exact:true}).click();await expect(page.getByRole('heading',{name:'助手',exact:true})).toBeVisible();await expect(page.getByLabel('已选课程资料')).toContainText('微积分讲义.md');expect(runs).toBe(0);
 await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.locator('.message.assistant').last()).toContainText('微积分');expect(runs).toBe(1);
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();await expect(page.locator('.kb-file')).toHaveCount(2);
});

test('library upload keeps failed files retryable and narrow windows retain stationary navigation',async({page})=>{
 await enter(page);await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();
 await page.getByRole('button',{name:'上传资料',exact:true}).click();const dialog=page.getByRole('dialog',{name:'上传资料',exact:true});
 await dialog.getByLabel('选择资料文件',{exact:true}).setInputFiles([{name:'成功.md',mimeType:'text/markdown',buffer:Buffer.from('有效讲义')},{name:'失败.pdf',mimeType:'application/pdf',buffer:Buffer.from('not pdf')}]);
 await dialog.getByRole('button',{name:'添加到资料库',exact:true}).click();await expect(dialog).toContainText('失败.pdf');await expect.poll(()=>page.request.get('/api/knowledge/library').then(r=>r.json()).then(d=>d.all_count)).toBe(1);
 await dialog.getByRole('button',{name:'关闭上传资料',exact:true}).click();await expect(page.locator('.kb-file')).toHaveCount(1);
 for(const width of [1280,768,390,320]){
  await page.setViewportSize({width,height:782});const sidebar=await page.locator('.workspace-sidebar').boundingBox();await page.locator('#workspace-content').evaluate(el=>el.scrollTop=500);const after=await page.locator('.workspace-sidebar').boundingBox();expect(after!.y).toBe(sidebar!.y);
  expect(await page.locator('#workspace-content').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 }
});

test('a delayed selected source cannot attach to a newly created conversation',async({page})=>{
 await enter(page);await seed(page);await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();await page.getByRole('button',{name:'查看 微积分讲义.md',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'文件详情'})).toContainText('段落1');let release!:()=>void;const wait=new Promise<void>(r=>release=r);let seen=false;
 await page.route('**/api/knowledge/sources/*',async route=>{if(route.request().method()==='GET'){seen=true;const response=await route.fetch();await wait;await route.fulfill({response});}else await route.continue();});
 await page.getByRole('button',{name:'用这份资料提问',exact:true}).click();await expect.poll(()=>seen).toBe(true);
 await page.getByRole('button',{name:'新会话',exact:true}).click();await expect.poll(()=>page.request.get('/api/agent/threads').then(r=>r.json()).then(d=>d.length)).toBe(1);release();
 await page.waitForTimeout(250);await expect(page.getByLabel('已选课程资料')).toHaveCount(0);
});

test('lost upload response locks its course and retries the original operation once',async({page})=>{
 await enter(page);await seed(page);await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();let lost=false;
 await page.route('**/api/knowledge/documents',async route=>{if(!lost){lost=true;await route.fetch();await route.abort('failed');}else await route.continue();});
 await page.getByRole('button',{name:'上传资料',exact:true}).click();const dialog=page.getByRole('dialog',{name:'上传资料',exact:true});await dialog.getByLabel('选择资料文件').setInputFiles({name:'响应丢失.md',mimeType:'text/markdown',buffer:Buffer.from('作业说明')});await dialog.getByRole('button',{name:'添加到资料库'}).click();
 await expect(dialog.getByRole('button',{name:'重试失败文件'})).toBeVisible();await expect(dialog.getByLabel('所属课程',{exact:true})).toBeDisabled();await dialog.getByRole('button',{name:'重试失败文件'}).click();await expect(dialog).toBeHidden();
 expect((await page.request.get('/api/knowledge/library').then(r=>r.json())).all_count).toBe(3);
});

test('deleting the only final-page item reveals a valid remaining page',async({page})=>{
 await enter(page);await seed(page);const original=await page.request.get('/api/knowledge/library').then(r=>r.json());const real=original.items[0];let deleted=false;
 await page.route('**/api/knowledge/library?*',async route=>{const url=new URL(route.request().url());const offset=Number(url.searchParams.get('offset')||0);const fake=Array.from({length:50},(_,i)=>({...real,id:'synthetic-'+i,data:{...real.data,filename:'合成资料'+i+'.md'}}));if(!deleted)fake.push(real);await route.fulfill({json:{...original,all_count:fake.length,total:fake.length,items:fake.slice(offset,offset+50)}});});
 page.on('dialog',d=>d.accept());page.on('response',r=>{if(r.request().method()==='DELETE'&&r.url().includes(real.id))deleted=true;});
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();await page.getByRole('button',{name:'下一页'}).click();await page.getByRole('button',{name:'查看 '+real.data.filename,exact:true}).click();await page.getByRole('button',{name:'删除资料',exact:true}).click();await expect(page.getByRole('dialog',{name:'文件详情'})).toBeHidden();await expect(page.locator('.kb-file')).toHaveCount(50);
});

test('course changes discard delayed text searches and successful web saves use fresh operation keys',async({page})=>{
 await enter(page);await seed(page);await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();await page.getByText('网页资料与正文检索',{exact:true}).click();
 let release!:()=>void;const pending=new Promise<void>(r=>release=r);let seen=false;
 await page.route('**/api/knowledge/search',async route=>{seen=true;await pending;await route.fulfill({json:{mode:'keyword',items:[{source_id:'old',title:'迟到旧课程内容',location:'段落1',text:'不应出现在新筛选中'}]}});});
 await page.getByLabel('检索资料正文').fill('作业');await page.getByRole('button',{name:'检索正文',exact:true}).click();await expect.poll(()=>seen).toBe(true);await page.getByRole('button',{name:'未分类 2',exact:true}).click();release();await page.waitForTimeout(200);await expect(page.getByText('迟到旧课程内容',{exact:true})).toHaveCount(0);
 const keys:string[]=[];await page.route('**/api/knowledge/web',async route=>{keys.push(route.request().headers()['idempotency-key']);await route.fulfill({json:{id:'synthetic-web-'+keys.length,revision:1}});});
 for(let i=0;i<2;i++){await page.getByLabel('保存公开网页').fill('https://example.com/notes');await page.getByRole('button',{name:'保存网页',exact:true}).click();await expect(page.getByLabel('保存公开网页')).toHaveValue('');}
 expect(keys).toHaveLength(2);expect(keys[0]).not.toBe(keys[1]);
});


test('unclassified body search sends the same scope as the file list',async({page})=>{
 await enter(page);await seed(page);
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();
 await page.getByRole('button',{name:'未分类 2',exact:true}).click();await page.getByText('网页资料与正文检索',{exact:true}).click();
 const response=page.waitForResponse(r=>r.url().endsWith('/api/knowledge/search')&&r.request().method()==='POST');
 await page.getByLabel('检索资料正文').fill('微积分');await page.getByRole('button',{name:'检索正文',exact:true}).click();
 const result=await response;expect(result.request().postDataJSON()).toMatchObject({unclassified:true});expect((await result.json()).items).toHaveLength(2);
});
