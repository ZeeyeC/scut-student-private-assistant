import { test, expect } from "@playwright/test";

test("local entry skips login and import wizard explains first installation on narrow screen", async ({
  page,
}) => {
  test.skip(
    process.env.CAMPUS_E2E_MODE !== "local",
    "Dedicated local-mode test server",
  );
  await page.setViewportSize({ width: 390, height: 850 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "今天，专注几件事。" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "登录", exact: true }),
  ).toHaveCount(0);
  const owner = (await (await page.request.get("/api/me")).json()).id;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "今天，专注几件事。" }),
  ).toBeVisible();
  expect((await (await page.request.get("/api/me")).json()).id).toBe(owner);
  await page.getByRole("button", { name: "课表", exact: true }).click();
  await page.getByRole("button", { name: "导入华工课表", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导入华工课表" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "安装课表扩展" }),
  ).toBeVisible({ timeout: 10000 });
  await expect(
    dialog.getByText("chrome://extensions", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByText("edge://extensions", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "重新检测扩展", exact: true }),
  ).toBeVisible();
  await expect(dialog.getByText(/开启.*开发者模式/)).toBeVisible();
  expect(
    (await (await page.request.get("/api/browser-imports")).json()).length,
  ).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: test.info().outputPath("import-guide-mobile.png"), fullPage: true });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByRole("heading", { name: "模型连接" })).toBeVisible();
  await expect(page.getByLabel("API 密钥")).toHaveValue("");
  await page.getByLabel("API 地址").fill("http://provider.example/v1");
  await page.getByLabel("API 密钥").fill("synthetic-private-secret");
  await page.getByRole("button", {name: "保存模型配置"}).click();
  await expect(page.getByRole("alert")).toContainText("HTTPS");
  await expect(page.getByRole("alert")).not.toContainText("synthetic-private-secret");
  await page.getByLabel("API 地址").fill("https://openrouter.ai/api/v1");
  await page.getByRole("button", {name: "保存模型配置"}).click();
  await expect(page.getByRole("status")).toContainText("模型配置已保存");
  await expect(page.getByLabel("API 密钥")).toHaveValue("");
});
