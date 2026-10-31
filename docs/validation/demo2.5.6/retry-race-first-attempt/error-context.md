# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: execution-feedback.spec.ts >> lost save response retries the same operation without accumulating twice
- Location: frontend/e2e/execution-feedback.spec.ts:73:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('region', { name: '本次安排执行反馈', exact: true }).getByRole('button', { name: '重试保存执行反馈', exact: true })
    - locator resolved to <button type="button" data-variant="outline" class="inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:opacity-50 disabled:pointer-events-none px-4 py-2 min-h-10 border bg-white hover:bg-slate-50 workspace-button">重试保存执行反馈</button>
  - attempting click action
    - waiting for element to be visible, enabled and stable
  - element was detached from the DOM, retrying

```

# Page snapshot

```yaml
- generic [active] [ref=f1e1]:
  - generic [ref=f1e3]:
    - complementary [ref=f1e4]:
      - generic [ref=f1e5]: 课间
      - navigation "主导航" [ref=f1e7]:
        - button "今日" [ref=f1e8] [cursor=pointer]
        - button "日程" [ref=f1e13] [cursor=pointer]
        - button "任务" [ref=f1e17] [cursor=pointer]
        - button "助手" [ref=f1e22] [cursor=pointer]
      - generic [ref=f1e26]:
        - button "设置" [ref=f1e27] [cursor=pointer]
        - generic [ref=f1e30]: execution-dc445d29-fb7f-4949-9333-694a826a4458@example.com
        - button "退出登录" [ref=f1e31] [cursor=pointer]
    - main [ref=f1e32]:
      - generic [ref=f1e33]:
        - generic [ref=f1e34]:
          - heading "今日" [level=1] [ref=f1e35]
          - generic [ref=f1e36]: 10月14日 · 周三
        - generic [ref=f1e37]:
          - button "待确认" [ref=f1e38] [cursor=pointer]
          - button "安排今天" [ref=f1e43] [cursor=pointer]
      - generic [ref=f1e44]:
        - region "接下来" [ref=f1e45]:
          - generic [ref=f1e46]:
            - generic [ref=f1e47]: 接下来
            - heading [level=2] [ref=f1e49]:
              - button "执行反馈合成练习" [ref=f1e50] [cursor=pointer]
            - paragraph [ref=f1e51]: 尚未安排时间
            - generic [ref=f1e52]:
              - generic [ref=f1e53]: 未分类
              - button "开始专注" [ref=f1e54] [cursor=pointer]
          - generic [ref=f1e57]:
            - generic [ref=f1e58]:
              - heading "其他待办0" [level=2] [ref=f1e59]
              - button "全部任务" [ref=f1e60] [cursor=pointer]
            - button "添加任务" [ref=f1e64] [cursor=pointer]
        - region "今日安排" [ref=f1e66]:
          - generic [ref=f1e67]:
            - heading "今日安排" [level=2] [ref=f1e68]
            - button "查看日程" [ref=f1e69] [cursor=pointer]
          - button "19:00 执行反馈合成练习 · 练习第一步 19:00–20:00" [ref=f1e70] [cursor=pointer]:
            - time [ref=f1e71]: 19:00
            - generic [ref=f1e73]:
              - strong [ref=f1e74]: 执行反馈合成练习 · 练习第一步
              - generic [ref=f1e75]: 19:00–20:00
      - generic [ref=f1e76]:
        - button "执行与记录" [ref=f1e77] [cursor=pointer]
        - button "课后作业" [ref=f1e78] [cursor=pointer]
  - dialog "执行与记录" [ref=f1e80]:
    - banner [ref=f1e81]:
      - heading "执行与记录" [level=2] [ref=f1e82]
      - button "关闭执行与记录" [ref=f1e83] [cursor=pointer]
    - generic [ref=f1e87]:
      - generic [ref=f1e88]:
        - generic [ref=f1e89]:
          - heading "执行与记录" [level=2] [ref=f1e90]
          - paragraph [ref=f1e91]: 10月14日星期三
        - button "一键生成当日日程" [ref=f1e92] [cursor=pointer]
      - generic [ref=f1e93]:
        - heading "课后作业" [level=2] [ref=f1e94]
        - paragraph [ref=f1e95]: 当天课程结束、达到设置的等待时间后，打开奶娃时一起记下各门课的作业。
        - button "查看课后作业询问" [ref=f1e96] [cursor=pointer]
      - generic [ref=f1e97]:
        - generic [ref=f1e98]:
          - heading "今日课程" [level=2] [ref=f1e99]
          - paragraph [ref=f1e100]: 今天没有课程。
        - generic [ref=f1e101]:
          - heading "今日学习安排" [level=2] [ref=f1e102]
          - generic [ref=f1e103]:
            - strong [ref=f1e104]: 19:00–20:00
            - heading "执行反馈合成练习" [level=3] [ref=f1e105]
            - paragraph [ref=f1e106]: 本次执行已反馈
            - button "按计划时长记录估算" [disabled]
            - region "本次安排执行反馈" [ref=f1e107]:
              - heading "实际执行与反馈" [level=4] [ref=f1e108]
              - paragraph [ref=f1e109]: 本次计划：60 分钟
              - paragraph [ref=f1e110]: 已记录实际：25 分钟
              - paragraph [ref=f1e111]: 保存结果尚未确认。重试会使用同一次操作，避免重复累计。
              - alert [ref=f1e112]: "TypeError: Failed to fetch"
              - group [ref=f1e113]:
                - generic "执行与更正历史（1条）" [ref=f1e114] [cursor=pointer]
            - button "锁定时间" [ref=f1e115] [cursor=pointer]
      - generic [ref=f1e116]:
        - heading "今日固定事项" [level=2] [ref=f1e117]
        - paragraph [ref=f1e118]: 今天没有固定事项。
        - button "去待办与日程添加事项" [ref=f1e119] [cursor=pointer]
```

# Test source

```ts
  1   | import {workspace,inbox} from './workspace';
  2   | import { test, expect, type Page } from "@playwright/test";
  3   | import { fileURLToPath } from "node:url";
  4   |
  5   | async function seed(page: Page, estimatedMinutes = 60) {
  6   |   await page.clock.setFixedTime(new Date("2026-10-14T10:30:00Z"));
  7   |   await page.goto("/");
  8   |   await page.getByRole("button", { name: "创建账号", exact: true }).click();
  9   |   await page.getByLabel("邮箱").fill(`execution-${crypto.randomUUID()}@example.com`);
  10  |   await page.getByLabel("密码").fill("Student!Password2026");
  11  |   await page.getByRole("button", { name: "注册并登录" }).click();
  12  |   await expect(page.getByRole("heading", { name: "今日",exact:true })).toBeVisible();
  13  |   const ids = await page.evaluate(async (estimate) => {
  14  |     const csrf = (await (await fetch("/api/csrf")).json()).csrf_token;
  15  |     const write = async (path: string, body: unknown, method = "POST") => {
  16  |       const r = await fetch("/api" + path, { method, headers: {
  17  |         "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID(),
  18  |       }, body: JSON.stringify(body) });
  19  |       if (!r.ok) throw new Error(await r.text());
  20  |       return r.json();
  21  |     };
  22  |     const settings = await (await fetch("/api/settings")).json();
  23  |     settings.data = { ...settings.data, week1_monday: "2026-10-12", study_windows: [{ start: "19:00", end: "21:00" }], daily_limit_minutes: 240 };
  24  |     await write("/settings", settings, "PUT");
  25  |     const draft = await write("/drafts/assignment", { items: [{ title: "执行反馈合成练习", due_at: "2026-10-20T20:00:00+08:00" }] });
  26  |     const saved = await write(`/drafts/${draft.id}/confirm`, { revision: draft.revision });
  27  |     const tid = saved.saved_ids[0];
  28  |     const task = await (await fetch(`/api/tasks/${tid}`)).json();
  29  |     const steps = await write(`/tasks/${tid}/step-drafts`, { task_revision: task.revision, steps: [{
  30  |       key: "one", title: "练习第一步", description: "隔离合成资料", estimated_minutes: estimate, dependency_keys: [], acceptance_criteria: ["完成练习"],
  31  |     }] });
  32  |     await write(`/drafts/${steps.id}/confirm`, { revision: steps.revision });
  33  |     const plan = await write("/plan-drafts", { scope: "today" });
  34  |     await write(`/drafts/${plan.id}/confirm`, { revision: plan.revision });
  35  |     const blocks = await (await fetch("/api/plan-blocks")).json();
  36  |     return { tid, bid: blocks[0].id };
  37  |   }, estimatedMinutes);
  38  |   await page.reload();await workspace(page,'records');
  39  |   return ids;
  40  | }
  41  |
  42  | const feedback = (page: Page) => page.getByRole("region", { name: "本次安排执行反馈", exact: true });
  43  |
  44  | test("60 planned, 25 actual and unfinished survive refresh; correction retains history in both entrances", async ({ page }) => {
  45  |   const { tid } = await seed(page);
  46  |   const region = feedback(page);
  47  |   await expect(region).toContainText("本次计划：60 分钟");
  48  |   await expect(region).toContainText("实际投入：未知");
  49  |   await region.getByLabel("实际分钟", { exact: true }).fill("25");
  50  |   await region.getByLabel("整项任务状态").selectOption("open");
  51  |   await region.getByLabel("未完成原因（可不填）").selectOption("insufficient_time");
  52  |   await region.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  53  |   await expect(region).toContainText("已记录实际：25 分钟");
  54  |   const task = await (await page.request.get(`/api/tasks/${tid}`)).json();
  55  |   expect(task.data.status).toBe("open");
  56  |   await page.reload();await workspace(page,'records');
  57  |   await expect(region).toContainText("已记录实际：25 分钟");
  58  |   await region.locator("summary").click();
  59  |   await region.getByRole("button", { name: "更正此记录" }).click();
  60  |   await region.getByLabel("实际分钟", { exact: true }).fill("20");
  61  |   await region.getByRole("button", { name: "保存更正", exact: true }).click();
  62  |   await expect(region).toContainText("已记录实际：20 分钟");
  63  |   await expect(region).toContainText("手工补记 25 分钟 · 已被更正");
  64  |   const history = await (await page.request.get(`/api/tasks/${tid}/executions`)).json();
  65  |   expect(history.map((r: any) => r.data.actual_minutes).sort()).toEqual([20, 25]);
  66  |   await region.screenshot({ path: fileURLToPath(new URL("../../docs/validation/demo2.5.1/e2e/execution/corrected20.png", import.meta.url)) });
  67  |   await workspace(page,'tasks');await page.getByRole('button',{name:/执行反馈合成练习/}).click();await page.getByText('编辑与执行',{exact:true}).click();
  68  |   await expect(page.getByRole("region", { name: "步骤执行反馈", exact: true })).toContainText("已记录实际：20 分钟");
  69  |   await page.setViewportSize({ width: 390, height: 844 });
  70  |   expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBeTruthy();
  71  | });
  72  |
  73  | test("lost save response retries the same operation without accumulating twice", async ({ page }) => {
  74  |   const { tid } = await seed(page);
  75  |   const keys: string[] = [];
  76  |   let first = true;
  77  |   await page.route("**/api/executions", async route => {
  78  |     if (route.request().method() !== "POST") return route.continue();
  79  |     keys.push(route.request().headers()["idempotency-key"]);
  80  |     if (first) {
  81  |       first = false;
  82  |       const response = await route.fetch();
  83  |       expect(response.ok()).toBeTruthy();
  84  |       return route.abort("failed");
  85  |     }
  86  |     return route.continue();
  87  |   });
  88  |   const region = feedback(page);
  89  |   await region.getByLabel("实际分钟", { exact: true }).fill("25");
  90  |   await region.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  91  |   await expect(region.getByRole("button", { name: "重试保存执行反馈", exact: true })).toBeVisible();
> 92  |   await region.getByRole("button", { name: "重试保存执行反馈", exact: true }).click();
      |                                                                       ^ Error: locator.click: Test timeout of 30000ms exceeded.
  93  |   await expect(region).toContainText("已记录实际：25 分钟");
  94  |   expect(keys).toHaveLength(2);
  95  |   expect(keys[0]).toBe(keys[1]);
  96  |   const records = await (await page.request.get(`/api/tasks/${tid}/executions`)).json();
  97  |   expect(records).toHaveLength(1);
  98  |   const exported = await (await page.request.get("/api/data-export")).json();
  99  |   expect(exported.resources.filter((r: any) => r.kind === "planning_event" && r.data.event_type === "execution_changed")).toHaveLength(1);
  100 | });
  101 |
  102 | test("explicit zero remains distinct from no feedback", async ({ page }) => {
  103 |   const { tid } = await seed(page);
  104 |   const region = feedback(page);
  105 |   await expect(region).toContainText("实际投入：未知");
  106 |   await region.getByLabel("实际分钟", { exact: true }).fill("0");
  107 |   await region.getByLabel("本次执行结果").selectOption("not_started");
  108 |   await region.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  109 |   await expect(region).toContainText("已记录实际：0 分钟");
  110 |   await page.reload();await workspace(page,'records');
  111 |   await expect(region).toContainText("已记录实际：0 分钟");
  112 |   const result = await (await page.request.get(`/api/tasks/${tid}/execution-summary`)).json();
  113 |   expect(result.actual_minutes).toBe(0);
  114 | });
  115 |
  116 | test("each block shows its own observation when one step has several blocks", async ({ page }) => {
  117 |   await seed(page, 120);
  118 |   const first = feedback(page).nth(0), second = feedback(page).nth(1);
  119 |   await first.getByLabel("实际分钟", { exact: true }).fill("25");
  120 |   await first.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  121 |   await expect(first).toContainText("已记录实际：25 分钟");
  122 |   await expect(second).toContainText("实际投入：未知");
  123 |   await second.getByLabel("实际分钟", { exact: true }).fill("0");
  124 |   await second.getByLabel("本次执行结果").selectOption("not_started");
  125 |   await second.getByRole("button", { name: "保存执行反馈", exact: true }).click();
  126 |   await expect(second).toContainText("已记录实际：0 分钟");
  127 |   await expect(first).toContainText("已记录实际：25 分钟");
  128 | });
  129 |
  130 | test("step detail can bind manual feedback to an existing estimated block", async ({ page }) => {
  131 |   const {tid, bid} = await seed(page);
  132 |   await page.evaluate(async (id) => {
  133 |     const csrf = (await (await fetch('/api/csrf')).json()).csrf_token;
  134 |     const block = (await (await fetch('/api/plan-blocks')).json()).find((b:any)=>b.id===id);
  135 |     const r=await fetch('/api/plan-blocks/'+id,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({revision:block.revision,completed:true})});
  136 |     if(!r.ok) throw new Error(await r.text());
  137 |   },bid);
  138 |   await page.reload();await workspace(page,'records');
  139 |   await workspace(page,'tasks');await page.getByRole('button',{name:/执行反馈合成练习/}).click();await page.getByText('编辑与执行',{exact:true}).click();
  140 |   const region=page.getByRole("region",{name:"步骤执行反馈",exact:true});
  141 |   await region.getByLabel("对应的学习安排").selectOption(bid);
  142 |   await region.getByLabel("实际分钟",{exact:true}).fill("25");
  143 |   await region.getByRole("button",{name:"保存执行反馈",exact:true}).click();
  144 |   await expect(region).toContainText("已记录实际：25 分钟");
  145 |   const s=await (await page.request.get(`/api/tasks/${tid}/execution-summary`)).json();
  146 |   expect(s.planning_spent_minutes).toBe(25);
  147 |   expect(s.legacy_estimated_minutes).toBe(0);
  148 | });
  149 |
```
