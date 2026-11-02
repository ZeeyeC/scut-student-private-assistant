import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {visualFixture} from './ui-visual-fixture';
const output=fileURLToPath(new URL('../../docs/validation/demo2.9/visual/',import.meta.url));
const data=[['第三章 · 微分中值定理.pdf','高等数学','pdf',2516582,'2026-11-02'],['线性表与链表.pptx','数据结构','pptx',6081741,'2026-11-02'],['大学物理 · 第二章讲义.pdf','大学物理','pdf',3250586,'2026-11-01'],['高数习题课笔记.md','高等数学','md',18432,'2026-11-01'],['实验数据记录.xlsx','大学物理','xlsx',43008,'2026-10-31'],['数据结构课程说明.docx','数据结构','docx',131072,'2026-10-30'],['期中复习范围.pdf','高等数学','pdf',884736,'2026-10-29'],['阅读摘记.txt',null,'txt',6144,'2026-10-28']];

test('standalone library follows the accepted full-window reference',async({page})=>{
 await mkdir(output,{recursive:true});await page.setViewportSize({width:1280,height:782});await visualFixture(page);await page.clock.setFixedTime(new Date('2026-11-02T05:30:00Z'));
 const items=data.map(([filename,course,format,size,date],i)=>({id:'source-'+i,kind:'knowledge_source',revision:1,data:{filename,title:filename,format,course_id:course,course_name:course,course_missing:false,size_bytes:size,created_at:date+'T02:00:00Z',source_type:'document',chunk_count:1,truncated:false}}));
 await page.route('**/api/knowledge/library?*',route=>route.fulfill({json:{items,total:8,all_count:8,courses:[{id:'高等数学',name:'高等数学',count:3,missing:false},{id:'数据结构',name:'数据结构',count:2,missing:false},{id:'大学物理',name:'大学物理',count:2,missing:false}],unclassified_count:1}}));
 await page.goto('/');await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'课程资料',exact:true}).click();await expect(page.locator('.kb-file')).toHaveCount(8);await page.mouse.move(1279,781);await page.screenshot({path:output+'knowledge-desktop.png'});
 for(const width of [1024,768,560,390,320]){await page.setViewportSize({width,height:782});expect(await page.locator('#workspace-content').evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);const before=await page.locator('.workspace-sidebar').boundingBox();await page.locator('#workspace-content').evaluate(e=>e.scrollTop=200);expect((await page.locator('.workspace-sidebar').boundingBox())!.y).toBe(before!.y);}
});
