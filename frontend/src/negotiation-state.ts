export type IntentInterval = { starts_at: string; ends_at: string };
export type IntentForm = {
  description: string; target_date: string; horizon_days: string;
  protected_intervals: IntentInterval[]; preferred_intervals: IntentInterval[];
  reduced_daily_limit_minutes: string; keep_block_ids: string[];
};
export type IntentConditions = Omit<IntentForm, "horizon_days" | "reduced_daily_limit_minutes"> & {
  timezone: string; horizon_days: number; reduced_daily_limit_minutes: number | null;
};
export type NegotiationOperation = { path: string; method: "POST" | "PATCH"; body: Record<string, unknown>; idempotencyKey: string };
export function emptyIntentForm(): IntentForm {
  return { description:"",target_date:"",horizon_days:"7",protected_intervals:[],preferred_intervals:[],reduced_daily_limit_minutes:"",keep_block_ids:[] };
}
export function intentForm(data: IntentConditions): IntentForm {
  const local=(rows:IntentInterval[])=>rows.map(row=>({starts_at:constraintInput(row.starts_at,data.timezone),ends_at:constraintInput(row.ends_at,data.timezone)}));
  return {...structuredClone(data),protected_intervals:local(data.protected_intervals),preferred_intervals:local(data.preferred_intervals),horizon_days:String(data.horizon_days),reduced_daily_limit_minutes:data.reduced_daily_limit_minutes == null ? "" : String(data.reduced_daily_limit_minutes)};
}
export function intentConditions(form: IntentForm, timezone: string): IntentConditions {
  if (!form.description.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(form.target_date) || !timezone) throw new Error("请明确填写目标、开始日期和设置时区，不会自动猜测时段。");
  const days = Number(form.horizon_days), limit = form.reduced_daily_limit_minutes.trim() ? Number(form.reduced_daily_limit_minutes) : null;
  if (!Number.isInteger(days) || days<1 || days>7 || (limit !== null && (!Number.isInteger(limit) || limit<0))) throw new Error("范围需为1至7天，临时每日上限需为非负整数。");
  const instants=(rows:IntentInterval[])=>rows.map(row=>({starts_at:constraintInstant(row.starts_at,timezone),ends_at:constraintInstant(row.ends_at,timezone)}));
  return {...structuredClone(form),protected_intervals:instants(form.protected_intervals),preferred_intervals:instants(form.preferred_intervals),timezone,horizon_days:days,reduced_daily_limit_minutes:limit};
}
export function negotiationOperation(path: string, method: "POST" | "PATCH", body: Record<string, unknown>): NegotiationOperation {
  return {path,method,body:structuredClone(body),idempotencyKey:crypto.randomUUID()};
}
export function selectIntentId(intents: {id:string}[], saved: string | null) {
  return saved === "new" ? "new" : intents.some(i=>i.id===saved) ? saved! : intents.at(-1)?.id ?? "new";
}
import { constraintInput, constraintInstant } from "./constraint-time";
