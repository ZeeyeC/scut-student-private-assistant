import {workspace,inbox} from './workspace';
import { test, expect, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

async function enter(page: Page) {
  await page.clock.setFixedTime(new Date("2026-10-14T10:30:00Z"));
  await page.goto("/");
  await page.getByRole("button", {name:"创建账号",exact:true}).click();
  await page.getByLabel("邮箱").fill(`text-course-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button",{name:"注册并登录"}).click();
  await expect(page.getByRole("heading",{name:"今日",exact:true})).toBeVisible();
  await page.evaluate(async () => {
    const s=await (await fetch("/api/settings")).json();
    const token=(await (await fetch("/api/csrf")).json()).csrf_token;
    s.data.semester_name="2026秋季";s.data.week1_monday="2026-09-07";
    s.data.periods={"1":{start:"08:00",end:"08:45"},"2":{start:"08:50",end:"09:35"}};
    const response=await fetch("/api/settings",{method:"PUT",headers:{"Content-Type":"application/json","X-CSRF-Token":token,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(s)});
    if(!response.ok) throw new Error(await response.text());
  });
}

async function say(page: Page, text: string) {
  await page.getByRole("textbox",{name:"给助手的消息",exact:true}).fill(text);
  await page.getByRole("button",{name:"发送",exact:true}).click();
}

test("chat asks for weeks, patches only one course, resumes and saves reviewed timetable",async ({page}) => {
  await enter(page);
  await page.getByRole("button",{name:"助手",exact:true}).click();
  await say(page,"添加文字课表：高等数学周一1、2节，周次待补；英语周二1、2节，1-16周单周。");
  const review=page.getByRole("region",{name:"文字课表校对",exact:true});
  await expect(review).toBeVisible();
  expect(await review.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
  await expect(page.locator(".chat")).toContainText("第几周开始");
  await expect(review.getByRole("button",{name:"校对完成，准备保存"})).toHaveCount(0);
  expect(await (await page.request.get("/api/courses")).json()).toEqual([]);
  const original=await (await page.request.get("/api/drafts")).json();
  await say(page,"补充第3至8周，只改高等数学。");
  await expect(review.getByLabel("周次（如 1-16周(单)）",{exact:true}).first()).toHaveValue("3-8周");
  const updated=await (await page.request.get("/api/drafts")).json();
  expect(updated).toHaveLength(1);expect(updated[0].id).toBe(original[0].id);
  expect(updated[0].data.payload.candidates[1]).toEqual(original[0].data.payload.candidates[1]);
  await page.reload();await page.getByRole("button",{name:"助手",exact:true}).click();
  await expect(review).toBeVisible();await expect(review.getByRole("heading",{name:"对话原文"})).toBeVisible();
  await review.getByLabel("确认这些课程属于上述学期，且与当前设置一致").check();
  for(const checkbox of await review.getByLabel("已校对本课程全部填写值；空缺教师、教室或校区按未知保留").all()) await checkbox.check();
  await review.getByRole("button",{name:"检查导入差异",exact:true}).click();
  await expect(review).toContainText("将新增 2 条：高等数学、大学英语");
  await page.getByRole("complementary",{name:"草稿校对区"}).evaluate(e=>{e.scrollTop=0;});
  await page.getByRole("complementary",{name:"草稿校对区"}).screenshot({path:fileURLToPath(new URL("../../docs/validation/demo2.9/e2e/timetable-text-review.png",import.meta.url))});
  await review.getByRole("button",{name:"校对完成，准备保存",exact:true}).click();
  await expect(review).toContainText("课程将进入固定课表");
  await review.getByRole("button",{name:"确认保存",exact:true}).click();
  await expect(review).toHaveCount(0);
  expect(await (await page.request.get("/api/courses")).json()).toHaveLength(2);
  expect(await (await page.request.get("/api/tasks")).json()).toEqual([]);
});

test("timetable embedded chat shows one text review and keeps it when collapsed",async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await enter(page);await workspace(page,'import');
  let invalidAssetRequests=0;
  page.on("request",r=>{if(r.url().includes("timetable-assets/undefined"))invalidAssetRequests++;});
  await page.getByRole("button",{name:"文字导入",exact:true}).click();
  await say(page,"添加文字课表：数学周一1、2节，周次待补。");
  const review=page.getByRole("region",{name:"文字课表校对",exact:true});
  await expect(review).toHaveCount(1);await expect(review).toBeVisible();
  expect(await review.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
  await page.getByRole("button",{name:"文字导入",exact:true}).click();
  await expect(review).toHaveCount(1);await expect(review).toBeVisible();
  expect(invalidAssetRequests).toBe(0);
  expect(await (await page.request.get("/api/courses")).json()).toEqual([]);
});
