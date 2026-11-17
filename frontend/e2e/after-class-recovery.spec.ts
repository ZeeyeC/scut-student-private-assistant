import {workspace,inbox} from './workspace';
import { test, expect, type Page } from "@playwright/test";

async function setup(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("邮箱").fill(`pet-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  // Finish the initial open before seeding courses. Otherwise it may see the
  // new courses and open a modal over the manual-open button during its click.
  const bootstrap=page.waitForResponse(r=>r.url().endsWith('/api/after-class/open')&&r.request().method()==='POST');
  await page.getByRole("button", { name: "注册并登录" }).click();
  await (await bootstrap).finished();
  await expect(page.getByRole("heading", { name: "今日",exact:true })).toBeVisible();
  await page.evaluate(async () => {
    const csrf = (await (await fetch("/api/csrf")).json()).csrf_token;
    const write = async (path: string, body: unknown, method = "POST") => {
      const response = await fetch("/api" + path, { method, headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const settings = await (await fetch("/api/settings")).json();
    settings.data = { ...settings.data, week1_monday: "2026-10-12", periods: { "1": { start: "14:00", end: "15:00" } } };
    await write("/settings", settings, "PUT");
    const draft = await write("/drafts/timetable", { semester_label: "test", courses: ["数学", "物理"].map((name, index) => ({ source_key: `c${index}`, name, weekday: 3, weeks: [1], periods: [1] })) });
    await write(`/drafts/${draft.id}/confirm`, { revision: draft.revision });
  });
  await page.getByRole("button", { name: "课后作业", exact:true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

async function otherWindowSaves(page: Page, complete = false) {
  await page.evaluate(async all => {
    const csrf = (await (await fetch("/api/csrf")).json()).csrf_token;
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID() };
    const current = await (await fetch("/api/after-class/open", { method: "POST", headers, body: "{}" })).json();
    const courses = all ? current.courses : current.courses.filter((c: { name: string }) => c.name === "数学");
    const response = await fetch(`/api/after-class/${current.review.id}/submit`, { method: "POST", headers, body: JSON.stringify({ revision: current.review.revision, answers: courses.map((c: { key: string }) => ({ course_key: c.key, status: "none", items: [] })) }) });
    if (!response.ok) throw new Error(await response.text());
  }, complete);
}

test("conflict reload retains only unsubmitted courses and does not duplicate tasks", async ({ page }) => {
  await setup(page);
  await page.getByLabel("物理的作业情况").selectOption("homework");
  await page.getByRole("textbox", { name: "作业内容", exact: true }).fill("保留这道物理题");
  await otherWindowSaves(page);
  await page.getByRole("button", { name: "保存作业并加入日程" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "重新载入并保留未提交内容" }).click();
  await expect(page.getByLabel("数学的作业情况")).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "作业内容", exact: true })).toHaveValue("保留这道物理题");
  await page.getByRole("button", { name: "保存作业并加入日程" }).click();
  await expect(page.getByText("已保存 1 项作业", { exact: false })).toBeVisible();
  expect((await (await page.request.get("/api/tasks")).json()).length).toBe(1);
});

test("offline and stale forms can be discarded without a successful save", async ({ page }) => {
  await setup(page);
  await page.getByLabel("物理的作业情况").selectOption("homework");
  await page.getByRole("textbox", { name: "作业内容", exact: true }).fill("未提交的内容");
  await page.route("**/api/after-class/*/draft", route => route.abort());
  await page.getByRole("button", { name: "稍后填写" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "放弃本次输入并关闭" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // Restoring focus after a confirmation must not immediately reopen the form.
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("no homework does not save a hidden invalid estimate", async ({ page }) => {
  await setup(page);
  await page.getByLabel("物理的作业情况").selectOption("homework");
  await page.getByLabel("预计用时（分钟）").fill("");
  await page.getByLabel("物理的作业情况").selectOption("none");
  await page.getByRole("button", { name: "稍后填写" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("completed elsewhere preserves local text for review but disables stale submission", async ({ page }) => {
  await setup(page);
  await page.getByLabel("物理的作业情况").selectOption("homework");
  await page.getByRole("textbox", { name: "作业内容", exact: true }).fill("仍可查看这段输入");
  await otherWindowSaves(page, true);
  await page.getByRole("button", { name: "保存作业并加入日程" }).click();
  await page.getByRole("button", { name: "重新载入并保留未提交内容" }).click();
  await expect(page.getByRole("textbox", { name: "作业内容", exact: true })).toHaveValue("仍可查看这段输入");
  await expect(page.getByRole("button", { name: "保存作业并加入日程" })).toBeDisabled();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "放弃本次输入并关闭" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("retry after a lost save response replays the receipt without duplicate homework", async ({ page }) => {
  await setup(page);
  await page.getByLabel("物理的作业情况").selectOption("homework");
  await page.getByRole("textbox", { name: "作业内容", exact: true }).fill("只保存一次");
  let loseResponse = true;
  await page.route("**/api/after-class/*/submit", async route => {
    if (!loseResponse) { await route.continue(); return; }
    loseResponse = false;
    const committed = await route.fetch();
    expect(committed.ok()).toBe(true);
    await route.abort();
  });
  await page.getByRole("button", { name: "保存作业并加入日程" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "保存作业并加入日程" }).click();
  await expect(page.getByText("已保存 1 项作业", { exact: false })).toBeVisible();
  expect((await (await page.request.get("/api/tasks")).json()).length).toBe(1);
});

test("a removed course retains unsaved input outside the submission until explicitly discarded", async ({ page }) => {
  await setup(page);
  await page.getByLabel("数学的作业情况").selectOption("homework");
  await page.getByRole("textbox", { name: "作业内容", exact: true }).fill("停课后仍需保留的数学题");
  await page.evaluate(async () => {
    const course = (await (await fetch("/api/courses")).json()).find((c: any) => c.data.name === "数学");
    const token = (await (await fetch("/api/csrf")).json()).csrf_token;
    const response = await fetch("/api/calendar-exceptions", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token, "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ course_id: course.id, date: "2026-10-14", cancelled: true }) });
    if (!response.ok) throw new Error(await response.text());
  });
  await page.getByRole("button", { name: "保存作业并加入日程" }).click();
  await page.getByRole("button", { name: "重新载入并保留未提交内容" }).click();
  const retained = page.getByRole("region", { name: "未参与本次提交的输入" });
  await expect(retained).toContainText("停课后仍需保留的数学题");
  await expect(page.getByLabel("数学的作业情况")).toHaveCount(0);
  await page.getByLabel("物理的作业情况").selectOption("none");
  await page.getByRole("button", { name: "保存作业并加入日程" }).click();
  await expect(page.getByText("已保存 0 项作业", { exact: false })).toBeVisible();
  await expect(retained).toContainText("停课后仍需保留的数学题");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await expect(retained).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect((await (await page.request.get("/api/tasks")).json()).length).toBe(0);
});

test('calendar course details create and display homework linked to that lesson', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-10-14T10:30:00Z'));
  await setup(page);
  await page.getByRole('button', { name: '放弃本次输入并关闭' }).click();
  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: '日程', exact: true }).click();
  await page.locator('.fc-v-event').filter({ hasText: '数学' }).first().click({ position: { x: 4, y: 15 } });
  const homework = page.getByRole('region', { name: '这次课的作业' });
  // A named section is exposed as a region in the accessibility tree.
  await homework.getByRole('button', { name: '补记作业', exact: true }).click();
  await homework.getByLabel('作业内容', { exact: true }).fill('补记课程练习');
  await homework.getByLabel('预计用时（分钟，可留空）').fill('40');
  await homework.getByRole('button', { name: '生成作业草稿', exact: true }).click();
  await expect(homework.getByText(/来源课次/)).toContainText('数学');
  expect(await page.request.get('/api/tasks').then(r => r.json())).toEqual([]);
  await homework.getByRole('button', { name: '确认保存', exact: true }).click();
  await expect(homework.getByRole('button', { name: '数学 · 补记课程练习 · 未完成' })).toBeVisible();
  const tasks = await page.request.get('/api/tasks').then(r => r.json());
  expect(tasks).toHaveLength(1);
  expect(tasks[0].data.course_occurrence.original_date).toBe('2026-10-14');
  const steps = await page.request.get(`/api/tasks/${tasks[0].id}/steps`).then(r => r.json());
  expect(steps[0].data.estimated_minutes).toBe(40);
});

test('automatic check-in closes at midnight and its typed homework can be restored manually', async ({ page }) => {
  await page.clock.install();
  await page.route('**/api/after-class/open', async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (data.due && data.automatic) data.expires_at = new Date(Date.parse(data.server_now) + 60000).toISOString();
    await route.fulfill({ response, json: data });
  });
  await setup(page);
  await page.getByLabel('物理的作业情况').selectOption('homework');
  await page.getByRole('textbox', { name: '作业内容', exact: true }).fill('跨天仍可恢复的练习');
  await page.clock.fastForward(61000);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: '恢复历史课后草稿', exact: true }).click();
  await expect(page.getByRole('heading', { name: '补记课程作业', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '作业内容', exact: true })).toHaveValue('跨天仍可恢复的练习');
  expect(await page.request.get('/api/tasks').then(r => r.json())).toEqual([]);
});
