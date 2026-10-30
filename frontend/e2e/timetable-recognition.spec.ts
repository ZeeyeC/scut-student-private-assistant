import {workspace,inbox} from './workspace';
import { test, expect, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

async function enter(page: Page) {
  await page.clock.setFixedTime(new Date("2026-10-14T10:30:00Z"));
  await page.goto("/");
  await page.getByRole("button", {name:"创建账号",exact:true}).click();
  await page.getByLabel("邮箱").fill(`recognition-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button",{name:"注册并登录"}).click();
  await expect(page.getByRole("heading",{name:"今日",exact:true})).toBeVisible();
  await page.evaluate(async () => {
    const s = await (await fetch("/api/settings")).json();
    const token=(await (await fetch("/api/csrf")).json()).csrf_token;
    s.data.semester_name="2026秋季"; s.data.week1_monday="2026-09-07";
    s.data.periods={"1":{start:"08:00",end:"08:45"},"2":{start:"08:50",end:"09:35"}};
    const r=await fetch("/api/settings",{method:"PUT",headers:{"Content-Type":"application/json","X-CSRF-Token":token,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(s)});
    if (!r.ok) throw new Error(await r.text());
  });
  await workspace(page,'import');
}

async function selectFile(page: Page) {
  await page.getByLabel("课表图片或 PDF",{exact:true}).setInputFiles(fileURLToPath(new URL("./fixtures/scut-synthetic-two-pages.pdf", import.meta.url)));
  await page.getByLabel("我同意将这份课表的所有页面图片及文字发送给设置中的模型供应商",{exact:true}).check();
}

async function correct(page: Page) {
  const review=page.getByRole("region",{name:"课表识别校对",exact:true});
  await expect(review).toBeVisible();
  await expect(review.getByRole("button",{name:"校对完成，准备保存"})).toHaveCount(0);
  await expect(review.getByText("待核对：周次",{exact:true})).toBeVisible();
  await expect(review.getByLabel("已校对本课程全部填写值；空缺教师、教室或校区按未知保留")).toBeDisabled();
  await review.getByLabel("周次（如 1-16周(单)）",{exact:true}).fill("3-8周");
  await review.getByLabel("确认这些页面属于上述学期，且与当前设置一致").check();
  await review.getByLabel("已校对本课程全部填写值；空缺教师、教室或校区按未知保留").check();
  return review;
}

test("two-page PDF evidence, correction, difference preview and explicit course save",async ({page}) => {
  await enter(page); await selectFile(page);
  await page.getByRole("button",{name:"识别课表，生成校对草稿",exact:true}).click();
  const review=await correct(page);
  expect(await (await page.request.get("/api/courses")).json()).toEqual([]);
  await review.getByRole("button",{name:"第 2 页 · 课程名称：高等数学",exact:true}).click();
  await expect(review.getByLabel("原件页码")).toHaveValue("2");
  await expect(review.getByLabel("证据区域",{exact:true})).toBeVisible();
  await expect(review.getByAltText("课表原件第 2 页")).toBeVisible();
  await review.getByRole("button",{name:"检查导入差异",exact:true}).click();
  await expect(review).toContainText("将新增 1 条：高等数学");
  await expect(page.getByText("已识别，请校对下方课表草稿",{exact:true})).toBeVisible();
  await review.screenshot({path:fileURLToPath(new URL("../../docs/validation/demo2.5/e2e/timetable-recognition-review.png", import.meta.url))});
  await review.getByRole("button",{name:"校对完成，准备保存",exact:true}).click();
  await review.getByRole("button",{name:"确认保存",exact:true}).click();
  await expect(review).toHaveCount(0);
  const courses=await (await page.request.get("/api/courses")).json();
  expect(courses).toHaveLength(1); expect(courses[0].data.weeks).toEqual([3,4,5,6,7,8]);
  await page.reload();
  expect(await (await page.request.get("/api/courses")).json()).toEqual(courses);
});

test("lost upload response reuses the same private original; preview refreshes after edits",async ({page}) => {
  await enter(page);
  let lose=true;
  await page.route("**/api/timetable-assets",async route => {
    if(!lose){await route.continue();return;}
    lose=false;
    // Chromium interception omits file bytes from postData. Rebuild the same
    // synthetic upload with the original idempotency header, then lose its reply.
    const headers=route.request().headers(); delete headers["content-type"]; delete headers["content-length"];
    const r=await page.request.post(route.request().url(),{headers,multipart:{file:{
      name:"scut-synthetic-two-pages.pdf",mimeType:"application/pdf",
      buffer:readFileSync(fileURLToPath(new URL("./fixtures/scut-synthetic-two-pages.pdf",import.meta.url)))
    }}});
    expect(r.ok(), await r.text()).toBe(true); await route.abort();
  });
  await selectFile(page);
  await page.getByRole("button",{name:"识别课表，生成校对草稿",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:/Failed to fetch|NetworkError|Load failed/})).toBeVisible();
  await page.getByRole("button",{name:"识别课表，生成校对草稿",exact:true}).click();
  const review=await correct(page);
  const exported=await (await page.request.get("/api/data-export")).json();
  expect(exported.resources.filter((r:any)=>r.kind==="asset")).toHaveLength(1);
  await review.getByRole("button",{name:"检查导入差异",exact:true}).click();
  await expect(review).toContainText("将新增 1 条");
  await review.getByLabel("课程名称",{exact:true}).fill("数学修订");
  await expect(review.getByRole("button",{name:"校对完成，准备保存"})).toHaveCount(0);
  await expect(review.getByLabel("已校对本课程全部填写值；空缺教师、教室或校区按未知保留")).not.toBeChecked();
  await page.reload(); await workspace(page,'import');
  await expect(page.getByRole("region",{name:"课表识别校对",exact:true})).toBeVisible();
  expect((await (await page.request.get("/api/timetable-jobs")).json()).length).toBe(1);
});
