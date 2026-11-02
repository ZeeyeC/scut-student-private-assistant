import {test,expect,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

async function enter(page:Page){
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.getByLabel('邮箱').fill(`markdown-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');
 await page.getByRole('button',{name:'注册并登录'}).click();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();
}
// Mock only the model transport. The real runtime, rendering and history replay
// process synthetic message events; no paid model or personal profile is used.
async function reply(page:Page,chunks:string[],hold=false){
 const id='md-'+crypto.randomUUID();let tid='',user='',created=false,finished=!hold;
 const resource=()=>({id,kind:'agent_run',revision:1,data:{thread_id:tid,status:finished?'done':'running',event_counter:chunks.length+2}});
 await page.route('**/api/agent/runs',async route=>{
  if(route.request().method()!=='POST')return route.continue();
  const body=route.request().postDataJSON();tid=body.thread_id;user=body.message;created=true;
  await route.fulfill({json:resource()});
 });
 await page.route('**/api/agent/threads/*/runs',route=>route.fulfill({json:created?[resource()]:[]}));
 await page.route('**/api/agent/runs/'+id,route=>route.fulfill({json:resource()}));
 await page.route('**/api/agent/runs/'+id+'/events?*',route=>{
  const after=Number(new URL(route.request().url()).searchParams.get('after'));
  const events=[{run_id:id,seq:1,type:'message',payload:{role:'user',message_id:id+'-u',content:user}},
    ...chunks.slice(0,finished?chunks.length:1).map((delta,i)=>({run_id:id,seq:i+2,type:'message_delta',payload:{message_id:id+'-a',delta}})),
    ...(finished?[{run_id:id,seq:chunks.length+2,type:'done',payload:{}}]:[])];
  return route.fulfill({contentType:'text/event-stream',body:events.filter(e=>e.seq>after).map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')||': keepalive\n\n'});
 });
 return ()=>{finished=true};
}
async function send(page:Page,text='**用户保留原文**'){
 await page.getByLabel('给助手的消息').fill(text);await page.getByRole('button',{name:'发送',exact:true}).click();
}
const formatted=String.raw`## 学习安排

先做 **高数作业**，再复习。

1. 整理错题
2. 练习计算

> 按自己的节奏完成。

| 课程 | 内容 |
| --- | --- |
| 高数 | 积分 |

- [x] 示例清单

行内公式 $a^2+b^2=c^2$。

$$
\int_0^1 x\,dx=\frac{1}{2}
$$

另一种写法 \(x+1\) 和

\[ y=2x \]

[参考资料](https://example.com/lesson)

\`\`\`text
**代码原文** \(do_not_convert\) $cash$
\`\`\`
`.replaceAll('\\`','`');

test('assistant formats markdown and math, user remains literal and history renders the same',async({page})=>{
 await reply(page,[formatted]);await enter(page);await send(page);
 const answer=page.locator('.message.assistant');
 await expect(answer.locator('strong')).toHaveText('高数作业');
 await expect(answer.getByRole('heading',{name:'学习安排'})).toBeVisible();
 await expect(answer.locator('ol > li')).toHaveCount(2);await expect(answer.locator('blockquote')).toContainText('按自己的节奏');
 await expect(answer.locator('table tbody tr')).toHaveCount(1);
 await expect(answer.locator('.katex')).toHaveCount(4);await expect(answer.locator('pre code')).toContainText('**代码原文** \\(do_not_convert\\) $cash$');
 await expect(answer.getByRole('checkbox')).toBeDisabled();
 await expect(page.locator('.message.user')).toContainText('**用户保留原文**');await expect(page.locator('.message.user strong')).toHaveCount(0);
 expect(await page.request.get('/api/tasks').then(r=>r.json())).toEqual([]);
 await page.reload();await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'助手',exact:true}).click();
 await expect(answer.locator('strong')).toHaveText('高数作业');await expect(answer.locator('.katex')).toHaveCount(4);
});

test('split markdown and math stay readable while animation frames are suspended',async({page})=>{
 const finish=await reply(page,['首段 **重','点**，公式 $x^2$，后续收到。\n\n$$\\badcommand{$$'],true);
 await enter(page);await page.evaluate(()=>{window.requestAnimationFrame=()=>0});await send(page,'流式显示');
 const answer=page.locator('.message.assistant');await expect(answer).toContainText('首段');finish();
 await expect(answer.locator('strong')).toHaveText('重点');await expect(answer).toContainText('后续收到');
 await expect(answer.locator('.katex').first()).toBeVisible();await expect(answer).toContainText('badcommand');
 await expect(page.getByRole('button',{name:'新会话',exact:true})).toBeEnabled();
});

test('model HTML, unsafe links, image URLs and trusted math macros cause no execution or external requests',async({page})=>{
 const external:string[]=[];page.on('request',r=>{if(r.url().includes('markdown-tracker.invalid'))external.push(r.url())});
 await reply(page,[String.raw`**正常文字**

<script>window.markdownExecuted=true</script><img src="https://markdown-tracker.invalid/raw" onerror="window.markdownExecuted=true">

[危险脚本](javascript:alert(1)) [本机文件](file:///tmp/private)

![跟踪图片](https://markdown-tracker.invalid/image)

$\href{https://markdown-tracker.invalid/math}{点击}$

$\includegraphics{https://markdown-tracker.invalid/asset}$`]);
 await enter(page);await send(page);
 const answer=page.locator('.message.assistant');await expect(answer.locator('strong')).toHaveText('正常文字');
 await expect(page.getByRole('button',{name:'新会话',exact:true})).toBeEnabled();
 expect(await page.evaluate(()=>(window as any).markdownExecuted)).toBeUndefined();
 await expect(answer.locator('script,img')).toHaveCount(0);
 expect(await answer.locator('a').evaluateAll(ns=>ns.every(n=>!n.getAttribute('href')||/^(https?:|#)/.test(n.getAttribute('href')!)))).toBe(true);
 expect(external).toEqual([]);
});

test('long tables code and formulas scroll inside narrow chat; copy preserves code',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const code='const longValue = "'+'a'.repeat(160)+'";';
 const table='| 第一栏 | 第二栏 | 第三栏 | 第四栏 | 第五栏 | 第六栏 |\n| --- | --- | --- | --- | --- | --- |\n| 长内容一 | 长内容二 | 长内容三 | 长内容四 | 长内容五 | 长内容六 |';
 await reply(page,[table+'\n\n```javascript\n'+code+'\n```\n\n$$x_1+x_2+x_3+x_4+x_5+x_6+x_7+x_8+x_9+x_{10}=123456789$$\n\nhttps://example.com/'+ 'long'.repeat(60)]);
 await enter(page);await send(page,'窄窗口');const answer=page.locator('.message.assistant');
 await expect(answer.locator('table')).toBeVisible();await expect(answer.locator('.katex')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(await answer.evaluate(n=>n.getBoundingClientRect().right<=innerWidth)).toBe(true);
 await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(text:string)=>{(window as any).copiedMarkdownCode=text}}}));
 await answer.getByRole('button',{name:'复制代码',exact:true}).click();
 expect(await page.evaluate(()=>(window as any).copiedMarkdownCode)).toBe(code+'\n');
 await page.getByLabel('给助手的消息').fill('继续');await expect(page.getByRole('button',{name:'发送',exact:true})).toBeEnabled();
 await page.screenshot({path:fileURLToPath(new URL('../../docs/validation/demo2.9.2/markdown-narrow.png',import.meta.url)),fullPage:true});
});
