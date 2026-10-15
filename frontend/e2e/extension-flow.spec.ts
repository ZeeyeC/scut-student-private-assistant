import { test, expect, chromium } from "@playwright/test";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
test("test-only school tab auto capture survives reload and does not duplicate opening", async () => {
  test.skip(
    !!process.env.SCUT_E2E_LIST,
    "This test uses the generic test fixture adapter",
  );
  const profile = await mkdtemp(path.join(tmpdir(), "campus-extension-"));
  const ext = path.resolve("../extension/.output-e2e/chrome-mv3");
  const context = await chromium.launchPersistentContext(profile, {
    channel: "chromium",
    headless: true,
    args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`],
  });
  try {
    await context.route("https://fixture.scut.edu.cn/**", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<!doctype html><meta charset="utf-8"><h1>仅用于测试的模拟学校</h1><button onclick="document.getElementById(\'content\').hidden=false;this.remove()">本人进入课表（模拟）</button><div id="content" hidden><p id="semester">测试学期</p><table id="fixture-timetable"><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th></tr><tr><td>自动提取测试数学</td><td>1</td><td>1-8周(单)</td><td>1-2</td><td>A101</td></tr></table></div>',
      }),
    );
    const page = await context.newPage();
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "创建账号", exact: true }).click();
    await page.getByLabel("邮箱").fill(`extension-${Date.now()}@example.com`);
    await page.getByLabel("密码").fill("Student!Password2026");
    await page.getByRole("button", { name: "注册并登录" }).click();
    await page.getByRole("button", { name: "课表", exact: true }).click();
    const newTab = context.waitForEvent("page");
    await page.getByRole("button", { name: "导入华工课表" }).click();
    await page.getByRole("button", { name: "打开教务并继续" }).click();
    const school = await newTab;
    await school.waitForURL("https://fixture.scut.edu.cn/");
    await expect(page.getByRole("status")).toContainText("教务已打开");
    await page.reload();
    await page.getByRole("button", { name: "课表", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("教务已打开");
    await school.bringToFront();
    await school.waitForTimeout(3000); // Keep the school foreground while its stable-load timer runs.
    expect((await (await page.request.get("/api/drafts")).json()).length).toBe(
      0,
    );
    await expect(page.getByRole("heading", { name: "课表预览" })).toHaveCount(
      0,
    );
    await school.getByRole("button", { name: "本人进入课表（模拟）" }).click();
    await expect(page.getByRole("heading", { name: "课表预览" })).toBeVisible({
      timeout: 20000,
    });
    await expect(page.locator('input[value="自动提取测试数学"]')).toBeVisible();
    expect(
      context
        .pages()
        .filter((p) => p.url().startsWith("https://fixture.scut.edu.cn"))
        .length,
    ).toBe(1);
    await page.getByRole("button", { name: "校对完成，准备保存" }).click();
    await page.getByRole("button", { name: "确认保存", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("已保存");
    const manifest = JSON.parse(
      await readFile(path.join(ext, "manifest.json"), "utf8"),
    );
    expect(manifest.permissions).not.toEqual(
      expect.arrayContaining(["cookies", "debugger", "webRequest"]),
    );
    expect(manifest.host_permissions).not.toContain("<all_urls>");
  } finally {
    await context.close();
    await rm(profile, { recursive: true, force: true });
  }
});
