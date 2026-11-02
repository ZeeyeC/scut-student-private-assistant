import {workspace,inbox} from './workspace';
import { test, expect, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

async function seed(page: Page, estimatedMinutes = 60) {
  await page.clock.setFixedTime(new Date("2026-10-14T10:30:00Z"));
  await page.goto("/");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("邮箱").fill(`execution-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: "今日",exact:true })).toBeVisible();
  const ids = await page.evaluate(async (estimate) => {
    const csrf = (await (await fetch("/api/csrf")).json()).csrf_token;
    const write = async (path: string, body: unknown, method = "POST") => {
      const r = await fetch("/api" + path, { method, headers: {
        "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID(),
      }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    };
    const settings = await (await fetch("/api/settings")).json();
    settings.data = { ...settings.data, week1_monday: "2026-10-12", study_windows: [{ start: "19:00", end: "21:00" }], daily_limit_minutes: 240 };
    await write("/settings", settings, "PUT");
    const draft = await write("/drafts/assignment", { items: [{ title: "执行反馈合成练习", due_at: "2026-10-20T20:00:00+08:00" }] });
    const saved = await write(`/drafts/${draft.id}/confirm`, { revision: draft.revision });
    const tid = saved.saved_ids[0];
    const task = await (await fetch(`/api/tasks/${tid}`)).json();
    const steps = await write(`/tasks/${tid}/step-drafts`, { task_revision: task.revision, steps: [{
      key: "one", title: "练习第一步", description: "隔离合成资料", estimated_minutes: estimate, dependency_keys: [], acceptance_criteria: ["完成练习"],
    }] });
    await write(`/drafts/${steps.id}/confirm`, { revision: steps.revision });
    const plan = await write("/plan-drafts", { scope: "today" });
    await write(`/drafts/${plan.id}/confirm`, { revision: plan.revision });
    const blocks = await (await fetch("/api/plan-blocks")).json();
    return { tid, bid: blocks[0].id };
  }, estimatedMinutes);
  await page.reload();await workspace(page,'records');
  return ids;
}

const feedback = (page: Page) => page.getByRole("region", { name: "本次安排执行反馈", exact: true });

test("60 planned, 25 actual and unfinished survive refresh; correction retains history in both entrances", async ({ page }) => {
  const { tid } = await seed(page);
  const region = feedback(page);
  await expect(region).toContainText("本次计划：60 分钟");
  await expect(region).toContainText("实际投入：未知");
  await region.getByLabel("实际分钟", { exact: true }).fill("25");
  await region.getByLabel("整项任务状态").selectOption("open");
  await region.getByLabel("未完成原因（可不填）").selectOption("insufficient_time");
  await region.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  await expect(region).toContainText("已记录实际：25 分钟");
  const task = await (await page.request.get(`/api/tasks/${tid}`)).json();
  expect(task.data.status).toBe("open");
  await page.reload();await workspace(page,'records');
  await expect(region).toContainText("已记录实际：25 分钟");
  await region.locator("summary").click();
  await region.getByRole("button", { name: "更正此记录" }).click();
  await region.getByLabel("实际分钟", { exact: true }).fill("20");
  await region.getByRole("button", { name: "保存更正", exact: true }).click();
  await expect(region).toContainText("已记录实际：20 分钟");
  await expect(region).toContainText("手工补记 25 分钟 · 已被更正");
  const history = await (await page.request.get(`/api/tasks/${tid}/executions`)).json();
  expect(history.map((r: any) => r.data.actual_minutes).sort()).toEqual([20, 25]);
  await region.screenshot({ path: fileURLToPath(new URL("../../docs/validation/demo2.9/e2e/execution/corrected20.png", import.meta.url)) });
  await workspace(page,'tasks');await page.getByRole('button',{name:/执行反馈合成练习/}).click();await page.getByText('编辑与执行',{exact:true}).click();
  await expect(page.getByRole("region", { name: "步骤执行反馈", exact: true })).toContainText("已记录实际：20 分钟");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBeTruthy();
});

test("lost save response retries the same operation without accumulating twice", async ({ page }) => {
  const { tid } = await seed(page);
  const keys: string[] = [];
  let first = true;
  await page.route("**/api/executions", async route => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"]);
    if (first) {
      first = false;
      const response = await route.fetch();
      expect(response.ok()).toBeTruthy();
      return route.abort("failed");
    }
    return route.continue();
  });
  const region = feedback(page);
  await region.getByLabel("实际分钟", { exact: true }).fill("25");
  await region.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  const retryButton = region.getByRole("button", { name: "重试保存执行反馈", exact: true });
  await expect(retryButton).toBeVisible();
  await page.evaluate(() => {
    window.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("focus"));
  });
  await expect(region).toContainText("已记录实际：25 分钟");
  await expect(retryButton).toBeVisible();
  await retryButton.click();
  await expect(region).toContainText("执行反馈已保存；计划时长和任务完成分别保留。");
  await expect(region).toContainText("已记录实际：25 分钟");
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const records = await (await page.request.get(`/api/tasks/${tid}/executions`)).json();
  expect(records).toHaveLength(1);
  const exported = await (await page.request.get("/api/data-export")).json();
  expect(exported.resources.filter((r: any) => r.kind === "planning_event" && r.data.event_type === "execution_changed")).toHaveLength(1);
});

test("explicit zero remains distinct from no feedback", async ({ page }) => {
  const { tid } = await seed(page);
  const region = feedback(page);
  await expect(region).toContainText("实际投入：未知");
  await region.getByLabel("实际分钟", { exact: true }).fill("0");
  await region.getByLabel("本次执行结果").selectOption("not_started");
  await region.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  await expect(region).toContainText("已记录实际：0 分钟");
  await page.reload();await workspace(page,'records');
  await expect(region).toContainText("已记录实际：0 分钟");
  const result = await (await page.request.get(`/api/tasks/${tid}/execution-summary`)).json();
  expect(result.actual_minutes).toBe(0);
});

test("each block shows its own observation when one step has several blocks", async ({ page }) => {
  await seed(page, 120);
  const first = feedback(page).nth(0), second = feedback(page).nth(1);
  await first.getByLabel("实际分钟", { exact: true }).fill("25");
  await first.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  await expect(first).toContainText("已记录实际：25 分钟");
  await expect(second).toContainText("实际投入：未知");
  await second.getByLabel("实际分钟", { exact: true }).fill("0");
  await second.getByLabel("本次执行结果").selectOption("not_started");
  await second.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  await expect(second).toContainText("已记录实际：0 分钟");
  await expect(first).toContainText("已记录实际：25 分钟");
});

test("step detail can bind manual feedback to an existing estimated block", async ({ page }) => {
  const {tid, bid} = await seed(page);
  await page.evaluate(async (id) => {
    const csrf = (await (await fetch('/api/csrf')).json()).csrf_token;
    const block = (await (await fetch('/api/plan-blocks')).json()).find((b:any)=>b.id===id);
    const r=await fetch('/api/plan-blocks/'+id,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({revision:block.revision,completed:true})});
    if(!r.ok) throw new Error(await r.text());
  },bid);
  await page.reload();await workspace(page,'records');
  await workspace(page,'tasks');await page.getByRole('button',{name:/执行反馈合成练习/}).click();await page.getByText('编辑与执行',{exact:true}).click();
  const region=page.getByRole("region",{name:"步骤执行反馈",exact:true});
  await region.getByLabel("对应的学习安排").selectOption(bid);
  await region.getByLabel("实际分钟",{exact:true}).fill("25");
  await region.getByRole("button",{name:"保存执行反馈",exact:true}).click();
  await expect(region).toContainText("已记录实际：25 分钟");
  const s=await (await page.request.get(`/api/tasks/${tid}/execution-summary`)).json();
  expect(s.planning_spent_minutes).toBe(25);
  expect(s.legacy_estimated_minutes).toBe(0);
});
