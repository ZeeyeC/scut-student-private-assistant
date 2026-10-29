import type { Resource } from "./types";
export type ReviewAction = "accept" | "reject" | "restore" | "reason";
export type PlanTotal = { status: "complete" | "partial" | "missing"; minutes: number | null; known_minutes: number; covered_dates: string[]; snapshot_ids: string[]; blocks: { plan_block_id: string; title: string; seconds: number; snapshot_ids: string[] }[]; gaps: string[] };
export type ReviewRecord = { record_id: string; task_id: string; task_title: string; step_id?: string; plan_block_ids: string[]; source: string; performed_on: string; timezone: string; observed_seconds: number | null; actual_seconds: number | null; feedback: string; unfinished_reason: string | null; reason_prompt: string | null; supersedes_id: string | null; timer_id?: string; allocation_status: string };
export type ReviewState = { id?: string | null; revision: number; data: { status: string; reason: string | null; history: { action: ReviewAction; reason: string | null; recorded_at: string; source_revision: number }[] } };
export type WeeklyReviewView = {
  week_start: string; week_end: string; timezone: string; source_revision: number;
  plans: Record<"original" | "adjusted" | "current", PlanTotal>;
  execution: { actual_seconds: number | null; observed_seconds: number | null; missing_plan_block_ids: string[]; ambiguous_record_ids: string[]; unconfirmed_execution_ids: string[]; completed_task_ids: string[]; undated_completed_task_ids: string[]; records: ReviewRecord[] };
  estimates: { allocated_minutes: number; allocations: { plan_block_id: string; minutes: number; baseline_id?: string }[]; unallocated: { step_id: string; plan_block_id?: string; minutes: number; baseline_id?: string }[] };
  gaps: string[]; review: ReviewState;
  next_week_plan?: {week_start:string;week_end:string;timezone:string;status:string;is_current_intent?:boolean;draft_id:string|null;draft:Resource|null;snapshot_ids:string[];reason:string|null};
};

export function mondayOf(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error("请选择有效日期");
  const day = new Date(value + "T12:00:00Z");
  if (Number.isNaN(day.getTime()) || day.toISOString().slice(0, 10) !== value) throw new Error("请选择有效日期");
  day.setUTCDate(day.getUTCDate() - (day.getUTCDay() + 6) % 7);
  return day.toISOString().slice(0, 10);
}

export function currentReviewWeek(timezone: string, now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const get = (kind: string) => parts.find(p => p.type === kind)!.value;
  return mondayOf(`${get("year")}-${get("month")}-${get("day")}`);
}

export function secondsLabel(seconds: number | null) {
  if (seconds === null) return "未知（缺少完整记录）";
  const whole = Math.floor(seconds);
  return whole % 60 ? `${Math.floor(whole / 60)} 分 ${whole % 60} 秒` : `${whole / 60} 分钟`;
}

export function reviewActionOperation(week: string, timezone: string, revision: number, sourceRevision: number, action: ReviewAction, reason: string) {
  if (mondayOf(week) !== week) throw new Error("周起始日期应为周一");
  new Intl.DateTimeFormat("zh-CN", { timeZone: timezone }).format();
  const note = reason.trim();
  if ((action === "accept" || action === "reason") && !note) throw new Error("请先写下想调整的内容或原因");
  if (note.length > 2000) throw new Error("内容请控制在 2000 字以内");
  return { idempotencyKey: crypto.randomUUID(), body: { week_start: week, timezone, revision, source_revision: sourceRevision, action, reason: note || null } };
}
export type ReviewOperation = ReturnType<typeof reviewActionOperation>;


export function reviewPlanOperation(report: Pick<WeeklyReviewView, 'week_start' | 'timezone' | 'source_revision' | 'review'>) {
  if (report.review.data.status !== 'accepted_pending_integration' || !report.review.data.reason?.trim()) throw new Error('请先接受一项有内容的调整意向');
  if (mondayOf(report.week_start) !== report.week_start) throw new Error('复盘周需要从周一开始');
  const target = new Date(report.week_start + 'T12:00:00Z');
  target.setUTCDate(target.getUTCDate() + 7);
  return {path:'/weekly-review/plan-draft', idempotencyKey:crypto.randomUUID(), targetWeek:target.toISOString().slice(0,10), body:{week_start:report.week_start, timezone:report.timezone, revision:report.review.revision, source_revision:report.source_revision}};
}
export type ReviewPlanOperation = ReturnType<typeof reviewPlanOperation>;

export function linkedPlanLabel(status: string) {
  return ({not_created:'尚未生成下周计划草稿',pending:'下周计划草稿等待确认',confirmed:'下周计划已确认',invalidated:'关联草稿已失效，请刷新后重新生成'} as Record<string,string>)[status] || '下周计划状态待核对';
}
