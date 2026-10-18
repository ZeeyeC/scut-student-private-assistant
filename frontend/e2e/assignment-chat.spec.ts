import { test, expect } from "@playwright/test";
import path from "node:path";

test("test vision draft needs review and agent write needs explicit approval", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 950 });
  await page.goto("/");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("邮箱").fill(`vision-${Date.now()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await page.getByRole("button", { name: "待办与日程", exact: true }).click();
  await page
    .getByLabel("作业截图")
    .setInputFiles(path.resolve("e2e/fixtures/synthetic-test.png"));
  await page
    .getByLabel("我同意将图片及课程候选发送给服务端配置的模型供应商")
    .check();
  await page.getByRole("button", { name: "识别并生成草稿" }).click();
  await expect(
    page.getByRole("heading", { name: "核对原图和识别结果" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "待校对的作业原图" }),
  ).toBeVisible();
  expect(await (await page.request.get("/api/tasks")).json()).toHaveLength(0);
  await page.getByRole("button", { name: "校对完成，准备保存" }).click();
  await page.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "数学练习", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "实验报告", exact: true }),
  ).toBeVisible();
  const tasks = await (await page.request.get("/api/tasks")).json();
  expect(tasks).toHaveLength(2);
  expect(tasks.every((t: any) => t.data.due_at === null)).toBe(true);
  await page.getByLabel("作业标题").fill("Agent 确认测试");
  await page.getByRole("button", { name: "生成校对草稿", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "核对任务草稿" }),
  ).toBeVisible();
  const drafts = await (await page.request.get("/api/drafts")).json();
  const draft = drafts.find(
    (d: any) => d.data.payload.items?.[0]?.title === "Agent 确认测试",
  );
  await page.getByRole("button", { name: "助手", exact: true }).click();
  // ToolModel's deterministic test-only command; no provider is called.
  await page.getByLabel("给助手的消息").fill("commit:" + draft.id);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "这一步需要你确认" }),
  ).toBeVisible();
  expect(await (await page.request.get("/api/tasks")).json()).toHaveLength(2);
  await page.getByRole("button", { name: "批准并执行" }).click();
  await expect(
    page.getByText("业务工具执行完毕", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "待办与日程", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Agent 确认测试", exact: true }),
  ).toHaveCount(1);
  expect(await (await page.request.get("/api/tasks")).json()).toHaveLength(3);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 2,
    ),
  ).toBe(true);
});
