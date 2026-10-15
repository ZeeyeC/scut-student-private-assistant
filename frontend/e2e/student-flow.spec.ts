import { test, expect } from "@playwright/test";
for (const width of [390, 768, 1440]) {
  test(`register, settings, assignment review, steps and plan at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 950 });
    await page.goto("/");
    await page.getByRole("button", { name: "创建账号", exact: true }).click();
    await page
      .getByLabel("邮箱")
      .fill(`student-${width}-${Date.now()}@example.com`);
    await page.getByLabel("密码").fill("Student!Password2026");
    await page.getByRole("button", { name: "注册并登录" }).click();
    await expect(
      page.getByRole("heading", { name: "今天，专注几件事。" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByLabel("学期名称").fill("真实 API 测试学期");
    await page.getByLabel("第一周周一").fill("2026-09-07");
    await page.getByRole("button", { name: "保存设置" }).click();
    await expect(page.getByRole("status")).toContainText("设置已保存");
    await page.reload();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await expect(page.getByLabel("学期名称")).toHaveValue("真实 API 测试学期");
    await page.getByRole("button", { name: "待办 / 作业", exact: true }).click();
    await page.getByLabel("作业标题").fill("写一篇实验报告");
    await page.getByLabel("要求（一行一项）").fill("解释实验结果");
    await page
      .getByRole("button", { name: "生成校对草稿", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "核对任务草稿" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "校对完成，准备保存" }).click();
    await page.getByRole("button", { name: "确认保存", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "写一篇实验报告" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "查看 / 拆解步骤" }).click();
    await page.getByRole("button", { name: "手工编辑步骤" }).click();
    await page.getByLabel("步骤标题").fill("整理实验数据");
    await page.getByLabel("具体行动").fill("制作数据表并解释异常");
    await page
      .getByLabel("完成标准（一行一项）")
      .fill("数据表完整，解释三处异常");
    await page.getByRole("button", { name: "生成可确认草稿" }).click();
    await expect(
      page.getByRole("heading", { name: "拆解草稿 · 耗时为估计" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "校对完成，准备保存" }).click();
    await page.getByRole("button", { name: "确认保存", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: /整理实验数据 · 剩余/ }),
    ).toBeVisible();
    await page.getByRole("button", { name: "今日", exact: true }).click();
    await page.getByRole("button", { name: "规划未来 7 天" }).click();
    await expect(
      page.getByRole("heading", { name: "未来 7 天计划" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "校对完成，准备保存" }).click();
    await page.getByRole("button", { name: "确认保存", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "未来 7 天计划" }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "助手", exact: true }).click();
    await page.getByLabel("给助手的消息").fill("查询作业");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect(
      page.getByText("业务工具执行完毕", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "助手", exact: true }).click();
    await expect(
      page.getByText("业务工具执行完毕", { exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}
