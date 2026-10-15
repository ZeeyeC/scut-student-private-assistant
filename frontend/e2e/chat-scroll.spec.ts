import { test, expect } from "@playwright/test";

// Synthetic messages, actual local backend and assistant-ui scroll handling.
// Catches a return button placed after history, or still visible at the bottom.
for (const width of [390, 1440]) {
  test(`latest-message button is reachable above old history at ${width}px`, async ({ page }) => {
    test.skip(process.env.CAMPUS_E2E_MODE !== "local", "Dedicated local-mode test server");
    await page.setViewportSize({ width, height: 950 });
    await page.goto("/");
    await page.getByRole("button", { name: "助手", exact: true }).click();
    await page.getByRole("button", { name: "新会话", exact: true }).click();
    const latest = page.getByRole("button", { name: "回到最新消息", exact: true });
    await expect(latest).toBeHidden();

    const history = Array.from({ length: 45 }, (_, i) => `测试历史第${i + 1}段：这是用于验证长对话滚动的合成消息。`).join("\n\n");
    await page.getByLabel("给助手的消息").fill(history);
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect(page.locator(".message.assistant").last()).toHaveText("业务工具执行完毕");
    await expect(page.getByRole("button", { name: "新会话", exact: true })).toBeEnabled();
    const viewport = page.locator(".chat-viewport");
    const bottomDistance = () => viewport.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight);
    await expect.poll(bottomDistance).toBeLessThan(20);
    await expect(latest).toBeHidden();

    await viewport.hover();
    await page.mouse.wheel(0, -900);
    await expect.poll(bottomDistance).toBeGreaterThan(500);
    await expect(latest).toBeVisible();
    await expect(latest).toBeEnabled();
    const vp = (await viewport.boundingBox())!;
    const button = (await latest.boundingBox())!;
    expect(button.y).toBeGreaterThanOrEqual(vp.y);
    expect(button.y + button.height).toBeLessThanOrEqual(vp.y + vp.height);
    expect(button.x).toBeGreaterThanOrEqual(vp.x);
    expect(button.x + button.width).toBeLessThanOrEqual(vp.x + vp.width);
    expect(button.y + button.height).toBeLessThan(950);
    await page.screenshot({ path: `/private/tmp/campus-chat-scroll-${width}.png` });
    // No locator auto-scroll: click where the button already appears on screen.
    await page.mouse.click(button.x + button.width / 2, button.y + button.height / 2);
    await expect.poll(bottomDistance).toBeLessThan(20);
    await expect(latest).toBeHidden();

    // Returning by keyboard works too; a fresh conversation hides the button.
    await viewport.hover();
    await page.mouse.wheel(0, -900);
    await expect(latest).toBeVisible();
    await latest.focus();
    await page.keyboard.press("Enter");
    await expect.poll(bottomDistance).toBeLessThan(20);
    await expect(latest).toBeHidden();
    await page.getByRole("button", { name: "新会话", exact: true }).click();
    await expect(page.locator(".message")).toHaveCount(0);
    await expect(latest).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
  });
}
