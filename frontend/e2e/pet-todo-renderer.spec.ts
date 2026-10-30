import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const html=readFileSync(new URL('../../campus-pet/Resources/PetTodo.html',import.meta.url),'utf8');

test('local pet renderer keeps task content as text and fixed controls reachable',async({page})=>{
 await page.setViewportSize({width:328,height:360});
 await page.addInitScript(()=>{(window as any).__actions=[];(window as any).webkit={messageHandlers:{todo:{postMessage:(v:unknown)=>(window as any).__actions.push(v)}}};});
 await page.route('**/pet-todo-test',r=>r.fulfill({contentType:'text/html',body:html}));await page.goto('/pet-todo-test');
 await expect.poll(()=>page.evaluate(()=>(window as any).__actions)).toEqual([{action:'ready'}]);
 const title='<img src=x onerror="window.bad=true">'+ '长任务'.repeat(30), tasks=[{id:'safe-1',title,time:'14:00'}];
 await page.evaluate(tasks=>(window as any).renderTodo({status:'list',tasks}),tasks);
 await expect(page.locator('.row button')).toHaveText(title);await expect(page.locator('img')).toHaveCount(0);
 await page.locator('.row button').click();expect(await page.evaluate(()=>(window as any).__actions.at(-1))).toEqual({action:'select',id:'safe-1'});
 await page.evaluate(({tasks,title})=>(window as any).renderTodo({status:'list',tasks,selected:'safe-1',detail:{title,time:'14:00',requirements:'要求\n'.repeat(80)}}),{tasks,title});
 for(const width of [328,240,194]){await page.setViewportSize({width,height:360});await page.locator('#body').evaluate(el=>el.scrollTop=el.scrollHeight);await expect(page.getByRole('button',{name:'标记完成',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'关闭待办窗口'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
 await page.getByRole('button',{name:'标记完成',exact:true}).click();expect(await page.evaluate(()=>(window as any).__actions.at(-1))).toEqual({action:'complete',id:'safe-1'});
 await page.evaluate(tasks=>(window as any).renderTodo({status:'list',tasks:tasks.map(t=>({...t,pending:true})),selected:'safe-1',error:'网络中断'}),tasks);
 await expect(page.getByRole('button',{name:'保存中…'})).toBeDisabled();await page.getByRole('button',{name:'刷新重试'}).click();expect(await page.evaluate(()=>(window as any).__actions.at(-1))).toEqual({action:'retry'});
});
