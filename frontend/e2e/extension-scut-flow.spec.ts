import { test, expect, chromium } from "@playwright/test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

for (const popup of [false, true]) {
  test(`SCUT measured DOM fixture ${popup ? "new tab" : "same tab"} requires a human query and survives MV3 restart`, async () => {
    test.setTimeout(75000);
    test.skip(
      !process.env.SCUT_E2E_LIST,
      "Run with the explicitly labeled SCUT DOM test adapter",
    );
    const profile = await mkdtemp(path.join(tmpdir(), "campus-scut-test-"));
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
          body: popup && !new URL(route.request().url()).search ? `<!doctype html><meta charset="utf-8"><h1>TEST ONLY：教务菜单</h1><button onclick="window.open('/?course=1', '_blank')">个人课表</button>` : `<!doctype html><meta charset="utf-8"><h1>TEST ONLY：实测结构，虚构课程</h1>
        <select id="xnm"><option selected>2026-2027</option></select><select id="xqm"><option selected>1</option><option>2</option></select>
        <button id="search_go" onclick="setTimeout(()=>document.querySelector('#kblist_table .pull-left').textContent='2026-2027学年第'+document.querySelector('#xqm').value+'学期',300)">查询</button>
        <div id="table1"><table id="kbgrid_table_0"><tr><td>已显示课表，等待本人选择学期</td></tr></table></div>
        <div id="table2" hidden><table id="kblist_table"><tr><td><div class="timetable_title"><h6 class="pull-left">2026-2027学年第1学期</h6>private-name<h6 class="pull-right">private-id</h6></div></td></tr>
        <tr><td id="xq_rowspan_4">星期四</td></tr><tr><td id="jc_4-1-2">1-2</td><td><div class="timetable_con"><span class="title"><font color="blue">专用适配测试课程</font></span><p><font>周数：1周,4-10周(双),11-15周(单)</font><font>校区:大学城校区 上课地点：测试室</font><font>教师 ：测试教师</font><font>教学班：test-class</font><font>教学班组成：private-group</font></p></div></td></tr></table></div>`,
        }),
      );
      const page = await context.newPage();
      await page.goto("http://127.0.0.1:5173/");
      if (process.env.CAMPUS_E2E_MODE !== "local") {
        await page.getByRole("button", { name: "创建账号", exact: true }).click();
        await page.getByLabel("邮箱").fill(`scut-${Date.now()}@example.com`);
        await page.getByLabel("密码").fill("Student!Password2026");
        await page.getByRole("button", { name: "注册并登录" }).click();
      } else {
        await expect(
          page.getByRole("heading", { name: "今天，专注几件事。" }),
        ).toBeVisible();
      }
      await page.getByRole("button", { name: "课表", exact: true }).click();
      // Create the unrelated tab before the import portal: Chromium otherwise
      // gives context.newPage() the active school tab as its real opener.
      const unrelated = popup ? await context.newPage() : null;
      if (unrelated) {
        await unrelated.goto("https://fixture.scut.edu.cn/?course=unrelated");
        await page.bringToFront();
      }
      const opened = context.waitForEvent("page");
      await page.getByRole("button", { name: "导入华工课表" }).click();
      await page.getByRole("button", { name: "打开教务并继续" }).click();
      const portal = await opened;
      let school = portal;
      await school.waitForURL("https://fixture.scut.edu.cn/");
      await page.getByRole("button", { name: "打开教务并继续" }).click();
      if (unrelated) {
        // A pre-existing same-domain page must not inherit this import.
        await unrelated.getByRole("button", { name: "查询", exact: true }).click();
        await unrelated.waitForTimeout(3500);
        expect(await (await page.request.get("/api/drafts")).json()).toHaveLength(0);
        await unrelated.close();
        const child = context.waitForEvent("page");
        await portal.getByRole("button", { name: "个人课表", exact: true }).click();
        school = await child;
        await school.waitForURL("https://fixture.scut.edu.cn/?course=1");
      }
      await school.bringToFront();
      await school.waitForTimeout(3500);
      expect(await (await page.request.get("/api/drafts")).json()).toHaveLength(
        0,
      );
      // Terminating this test-only worker exercises storage.session rehydration.
      const cdp = await context.newCDPSession(school);
      const { targetInfos } = await cdp.send("Target.getTargets");
      const worker = targetInfos.find(
        (t) =>
          t.type === "service_worker" && t.url.startsWith("chrome-extension://"),
      );
      expect(worker).toBeTruthy();
      await cdp.send("Target.closeTarget", { targetId: worker!.targetId });
      await page.reload();
      await page.getByRole("button", { name: "课表", exact: true }).click();
      await school.bringToFront();
      await school.locator("#xqm").selectOption({ label: "2" });
      await school.getByRole("button", { name: "查询", exact: true }).click();
      try {
        await expect(page.getByRole("heading", { name: "课表预览" })).toBeVisible(
          { timeout: 20000 },
        );
      } catch (e) {
        console.log(
          "TEST DEBUG",
          await (await page.request.get("/api/browser-imports")).json(),
          await school.locator("#kblist_table .pull-left").textContent(),
        );
        throw e;
      }
      await expect(page.locator('input[value="专用适配测试课程"]')).toBeVisible();
      const drafts = await (await page.request.get("/api/drafts")).json();
      expect(drafts[0].data.payload.semester_label).toBe("2026-2027学年第2学期");
      expect(JSON.stringify(drafts)).not.toMatch(
        /private-name|private-id|private-group/,
      );
      expect(drafts[0].data.payload.courses[0].weeks).toEqual([
        1, 4, 6, 8, 10, 11, 13, 15,
      ]);
      expect(
        context
          .pages()
          .filter((p) => p.url().startsWith("https://fixture.scut.edu.cn"))
          .length,
      ).toBe(popup ? 2 : 1);
      await page.getByRole("button", { name: "校对完成，准备保存" }).click();
      await page.getByRole("button", { name: "确认保存", exact: true }).click();
      await expect(page.getByRole("status")).toContainText("已保存");
    } finally {
      await context.close();
      await rm(profile, { recursive: true, force: true });
    }
  });

}
