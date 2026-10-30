import {workspace,inbox} from './workspace';
import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

test("pet repeatedly locates approval in an older conversation after opening a new one", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("邮箱").fill(`review-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: "今日",exact:true })).toBeVisible();
  const target = await page.evaluate(async () => {
    const token = (await (await fetch("/api/csrf")).json()).csrf_token;
    const post = async (path: string, body: unknown) => {
      const response = await fetch("/api" + path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token, "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const draft = await post("/drafts/assignment", { items: [{ title: "旧会话的待确认任务" }] });
    const pending = await post("/agent/threads", {});
    await post("/agent/runs", { thread_id: pending.id, message: "commit:" + draft.id });
    await post("/agent/threads", {});
    return pending.id;
  });
  await expect.poll(async () => (await (await page.request.get("/api/agent/pet-state")).json()).review_thread_id).toBe(target);
  await page.addScriptTag({ content: readFileSync(new URL("../../campus-pet/Resources/Bridge.js", import.meta.url), "utf8") });
  await page.evaluate(() => (window as any).__campusPet.showReview());
  await expect(page.getByRole("button", { name: "批准并执行", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "新会话", exact: true }).click();
  await expect(page.getByRole("button", { name: "批准并执行", exact: true })).toHaveCount(0);
  await page.evaluate(() => (window as any).__campusPet.showReview());
  await expect(page.getByRole("button", { name: "批准并执行", exact: true })).toBeVisible();
});

test("a late history response cannot replace the review selected by the pet", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("邮箱").fill(`race-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: "今日",exact:true })).toBeVisible();
  const runs = await page.evaluate(async () => {
    const token = (await (await fetch("/api/csrf")).json()).csrf_token;
    const post = async (path: string, body: unknown) => {
      const response = await fetch("/api" + path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token, "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await response.text()); return response.json();
    };
    const results = [];
    for (const title of ["目标审批", "过期请求的审批"]) {
      const draft = await post("/drafts/assignment", { items: [{ title }] });
      const thread = await post("/agent/threads", {});
      const run = await post("/agent/runs", { thread_id: thread.id, message: "commit:" + draft.id });
      results.push({ thread: thread.id, run: run.id });
    }
    return results;
  });
  for (const run of runs) await expect.poll(async () => (await (await page.request.get(`/api/agent/runs/${run.run}`)).json()).data.status).toBe("waiting_approval");
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let held = false, delivered = false;
  await page.route(`**/api/agent/threads/${runs[1].thread}/runs`, async route => {
    const response = await route.fetch(); held = true;
    await gate;
    try { await route.fulfill({ response }); } catch { /* expected when the stale request was cancelled */ }
    delivered = true;
  });
  await page.addScriptTag({ content: readFileSync(new URL("../../campus-pet/Resources/Bridge.js", import.meta.url), "utf8") });
  await expect.poll(() => held).toBe(true);
  await page.evaluate(() => (window as any).__campusPet.showReview());
  await expect(page.getByRole("region",{name:"助手操作确认",exact:true})).toContainText("目标审批");
  release(); await expect.poll(() => delivered).toBe(true);
  // Let the deliberately delayed callback and any resulting React effects settle.
  await page.waitForTimeout(300);
  await expect(page.getByRole("region",{name:"助手操作确认",exact:true})).toContainText("目标审批");
  await expect(page.getByRole("region",{name:"助手操作确认",exact:true})).not.toContainText("过期请求的审批");
});
