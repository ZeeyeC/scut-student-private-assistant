import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it } from "vitest";
import { WeeklyReview } from "./WeeklyReview";
import { currentReviewWeek } from "./weekly-review-state";

function render(actual: number | null, linkedStatus = "not_created") {
  const q = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const week = currentReviewWeek("Asia/Shanghai");
  q.setQueryData(["settings"], { data: { timezone: "Asia/Shanghai" } });
  const plan = { status: "partial", minutes: null, known_minutes: 60, covered_dates: [week], snapshot_ids: ["snapshot-ref"], blocks: [{ plan_block_id: "block-ref", title: "数学", seconds: 3600, snapshot_ids: ["snapshot-ref"] }], gaps: [] };
  q.setQueryData(["weekly-review", week, "Asia/Shanghai"], { week_start: week, week_end: "2026-11-02", timezone: "Asia/Shanghai", source_revision: 3,
    plans: { original: plan, adjusted: plan, current: { ...plan, status: "complete", minutes: 60 } },
    execution: { actual_seconds: actual, observed_seconds: actual, missing_plan_block_ids: actual === null ? ["block-ref"] : [], ambiguous_record_ids: [], unconfirmed_execution_ids: [], completed_task_ids: [], undated_completed_task_ids: [], records: [{ record_id: "execution-ref", task_id: "task", task_title: "数学", observed_seconds: actual, actual_seconds: actual, source: "manual", performed_on: week, timezone: "Asia/Shanghai", feedback: "partial", unfinished_reason: null, reason_prompt: "这次安排遇到了什么？", supersedes_id: null, plan_block_ids: ["block-ref"], allocation_status: "inside" }] },
    estimates: { allocated_minutes: 40, allocations: [{ plan_block_id: "block-ref", minutes: 40 }], unallocated: [] }, gaps: ["incomplete_original_baseline"], review: { revision: 1, data: { status: linkedStatus === "not_created" ? "awaiting_choice" : "accepted_pending_integration", reason: linkedStatus === "not_created" ? null : "希望提前学习", history: [] } },
    next_week_plan: {week_start:"2026-11-02", week_end:"2026-11-09", timezone:"Asia/Shanghai", status:linkedStatus, draft_id:linkedStatus === "not_created" ? null : "next-draft", is_current_intent:true, snapshot_ids:linkedStatus === "confirmed" ? ["approved-next-snapshot"] : [], reason:linkedStatus === "invalidated" ? "source_changed" : null,
      draft: linkedStatus !== "pending" ? null : {id:"next-draft", kind:"draft", revision:1, data:{draft_kind:"plan",status:"pending",source_revision:3,source:{generated_hash:"program-hash"},payload:{scope:"range",target_date:"2026-11-02",horizon_days:7,timezone:"Asia/Shanghai",warnings:[],unscheduled:[],blocks:[{id:"new-block",task_id:"task",step_id:"step",title:"下周数学复习",starts_at:"2026-11-02T09:00:00+08:00",ends_at:"2026-11-02T10:00:00+08:00",status:"planned",locked:false}]}}}} });
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
  expect(html).toContain("尚未生成下周计划草稿");
  expect(html).toContain("文字意向保留为来源");
  expect(html).not.toContain('aria-label="计划草稿"');
  expect(html).toContain("保存原因");
});

it("shows explicit zero and does not treat a partial execution as a completed task", () => {
  const html = render(0);
  expect(html).toContain("0 分钟");
  expect(html).toContain("本周有日期依据的任务完成：0 项");
  expect(html).toContain("部分完成");
});


it("renders the actual linked draft through original PlanReview and keeps approval explicit", () => {
  const html = render(null, "pending");
  expect(html).toContain('aria-label="计划草稿"');
  expect(html).toContain("下周数学复习");
  expect(html).toContain("校对完成，准备保存");
  expect(html).toContain("下周计划草稿等待确认");
  expect(html).not.toContain("已确认快照");
});

it("shows real approval evidence and makes stale drafts unavailable for confirmation", () => {
  const confirmed = render(0, "confirmed");
  expect(confirmed).toContain("下周计划已确认");
  expect(confirmed).toContain("approved-next-snapshot");
  expect(confirmed).toContain("恢复复盘意向会保留这些安排和快照");
  expect(confirmed).not.toContain('aria-label="计划草稿"');
  const stale = render(null, "invalidated");
  expect(stale).toContain("关联草稿已失效");
  expect(stale).not.toContain('aria-label="计划草稿"');
});
