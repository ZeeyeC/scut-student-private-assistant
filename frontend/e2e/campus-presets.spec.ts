import { test, expect, type Page } from "@playwright/test";

async function enter(page: Page) {
  await page.addInitScript(() => {
    (window as any).__importCalls = [];
    (window as any).__campusNative = {
      request: async (command: string, payload: any) => {
        (window as any).__importCalls.push({ command, payload });
        return { browser: "chrome", installed: true };
      },
    };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("邮箱").fill(`preset-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("密码").fill("Student!Password2026");
  await page.getByRole("button", { name: "注册并登录", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
}

test("settings preset selector fills 12 periods, custom edit marks custom, and import review defers atomic save", async ({
  page,
}) => {
  await enter(page);

  // 1. Empty import screen never shows preset selector
  await page.getByRole("button", { name: "日程", exact: true }).click();
  await page.getByRole("button", { name: "导入课表", exact: true }).click();
  const importDialog = page.getByRole("dialog", { name: "导入课表", exact: true });
  await expect(importDialog.getByLabel("校区节次模板")).toHaveCount(0);
  await page.keyboard.press("Escape");

  // 2. Settings -> 课程与学期 selector fills 12 periods and custom edits clear preset selection
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "课程与学期", exact: true }).click();
  const settingsDialog = page.getByRole("dialog", { name: "课程与学期", exact: true });
  await settingsDialog.getByLabel("学期名称").fill("2026秋季");
  await settingsDialog.getByLabel("第一周周一").fill("2026-10-12");

  const settingsPreset = settingsDialog.getByLabel("校区节次模板");
  await expect(settingsPreset).toHaveValue("");
  await settingsPreset.selectOption("wushan");
  await expect(settingsPreset).toHaveValue("wushan");
  await expect(settingsDialog.locator(".period-row")).toHaveCount(12);

  // Not saved to backend before clicking 保存设置
  expect((await (await page.request.get("/api/settings")).json()).data.campus_preset).toBeNull();

  // Manual edit to a period row marks custom (clears preset selection)
  await settingsDialog.locator(".period-row").first().getByLabel("开始").fill("08:05");
  await expect(settingsPreset).toHaveValue("");

  // Re-select guoji and save settings
  await settingsPreset.selectOption("guoji");
  await settingsDialog.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(settingsDialog.getByRole("status")).toContainText("设置已保存");
  expect((await (await page.request.get("/api/settings")).json()).data.campus_preset).toBe("guoji");
  await page.keyboard.press("Escape");

  // 3. Seed a school timetable draft and verify deferred selection & atomic save
  await page.evaluate(async () => {
    const csrf = (await (await fetch("/api/csrf")).json()).csrf_token;
    await fetch("/api/drafts/timetable", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        semester_label: "2026秋季",
        courses: [
          {
            source_key: "k1",
            name: "操作系统",
            campus: "五山",
            location: "3402",
            weekday: 1,
            weeks: [1, 2],
            periods: [1, 2],
          },
        ],
      }),
    });
  });

  await page.getByRole("button", { name: "日程", exact: true }).click();
  await page.getByRole("button", { name: "导入课表", exact: true }).click();
  const reviewPreset = importDialog.getByLabel("校区节次模板");
  await expect(reviewPreset).toHaveValue("guoji");

  // Change to daxuecheng after preview invalidates preview; settings remain "guoji" until final confirm
  await importDialog.getByRole("button", { name: "校对完成，准备保存", exact: true }).click();
  await expect(importDialog.getByRole("button", { name: "确认保存", exact: true })).toBeVisible();
  await reviewPreset.selectOption("daxuecheng");
  await expect(importDialog.getByRole("button", { name: "确认保存", exact: true })).toHaveCount(0);
  expect((await (await page.request.get("/api/settings")).json()).data.campus_preset).toBe("guoji");

  await importDialog.getByRole("button", { name: "校对完成，准备保存", exact: true }).click();
  await importDialog.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get("/api/settings")).json()).data.campus_preset).toBe("daxuecheng");
  const savedCourses = await (await page.request.get("/api/courses")).json();
  expect(savedCourses).toHaveLength(1);
  expect(savedCourses[0].data.campus).toBe("五山");
  expect(savedCourses[0].data.location).toBe("3402");
});
