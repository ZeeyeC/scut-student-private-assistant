import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it } from "vitest";
import { WeeklyReview } from "./WeeklyReview";
import { currentReviewWeek } from "./weekly-review-state";

function render(actual: number | null) {
  const q = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const week = currentReviewWeek("Asia/Shanghai");
  q.setQueryData(["settings"], { data: { timezone: "Asia/Shanghai" } });
  const plan = { status: "partial", minutes: null, known_minutes: 60, covered_dates: [week], snapshot_ids: ["snapshot-ref"], blocks: [{ plan_block_id: "block-ref", title: "数学", seconds: 3600, snapshot_ids: ["snapshot-ref"] }], gaps: [] };
  q.setQueryData(["weekly-review", week, "Asia/Shanghai"], { week_start: week, week_end: "2026-11-02", timezone: "Asia/Shanghai", source_revision: 3,
    plans: { original: plan, adjusted: plan, current: { ...plan, status: "complete", minutes: 60 } },
    execution: { actual_seconds: actual, observed_seconds: actual, missing_plan_block_ids: actual === null ? ["block-ref"] : [], ambiguous_record_ids: [], unconfirmed_execution_ids: [], completed_task_ids: [], undated_completed_task_ids: [], records: [{ record_id: "execution-ref", task_id: "task", task_title: "数学", observed_seconds: actual, actual_seconds: actual, source: "manual", performed_on: week, timezone: "Asia/Shanghai", feedback: "partial", unfinished_reason: null, reason_prompt: "这次安排遇到了什么？", supersedes_id: null, plan_block_ids: ["block-ref"], allocation_status: "inside" }] },
    estimates: { allocated_minutes: 40, allocations: [{ plan_block_id: "block-ref", minutes: 40 }], unallocated: [] }, gaps: ["incomplete_original_baseline"], review: { revision: 0, data: { status: "awaiting_choice", reason: null, history: [] } } });
  const html = renderToStaticMarkup(createElement(QueryClientProvider, { client: q }, createElement(WeeklyReview)));
  q.clear();
  return html;
}

it("separates partial baseline, unknown execution and legacy estimates, with trace references", () => {
  const html = render(null);
  expect(html).toContain("周基线不完整");
  expect(html).toContain("未知");
  expect(html).toContain("历史估算");
  expect(html).toContain("40 分钟");
  expect(html).toContain("snapshot-ref");
  expect(html).toContain("execution-ref");
  expect(html).toContain("这次安排遇到了什么");
  expect(html).toContain("等待排程联动");
  expect(html).toContain("保存原因");
});

it("shows explicit zero and does not treat a partial execution as a completed task", () => {
  const html = render(0);
  expect(html).toContain("0 分钟");
  expect(html).toContain("本周有日期依据的任务完成：0 项");
  expect(html).toContain("部分完成");
});
