import { currentReviewWeek, mondayOf } from "./weekly-review-state";
export type GoalSubtask = { id?: string; title: string; status: 'open' | 'completed'; estimated_minutes: number; task_id: string | null };
export type GoalValues = {
  title: string; description: string; deadline: string | null; weekly_budget_minutes: number; priority: number;
  load_category: 'study' | 'exercise' | 'other'; allowed_adjustment: 'reduce' | 'delay' | 'ask'; paused: boolean; subtasks: GoalSubtask[];
};
export type GoalView = { id: string; revision: number; source_revision: number; contract_version: 'goals-v1'; data: GoalValues & { source:'user'; confirmed:true; completion_history: {subtask_id:string; title:string; estimated_minutes:number; task_id:string | null; completed_at:string; goal_revision:number}[] }; references: {subtask_id:string; task_id:string; available:boolean; revision:number|null; title:string|null; status:string|null}[]; arrangements: unknown[] };
export type GoalsView = { contract_version:'goals-v1'; source_revision:number; goals:GoalView[]; capacity:{status:'unknown';weekly_available_minutes:null;integration_status:'pending'} };
export type GoalForm = Omit<GoalValues, 'deadline' | 'weekly_budget_minutes' | 'subtasks'> & {deadline:string; weekly_budget_minutes:string; subtasks:(Omit<GoalSubtask,'estimated_minutes' | 'task_id'> & {estimated_minutes:string; task_id:string})[]};
export type GoalWrite = {revision:number} & Partial<GoalValues>;
export type GoalOperation = {path:string;method:'POST'|'PATCH';body:GoalWrite;idempotencyKey:string};

export function goalForm(goal?: GoalView): GoalForm {
  if (!goal) return { title:'', description:'', deadline:'', weekly_budget_minutes:'', priority:2, load_category:'study', allowed_adjustment:'ask', paused:false, subtasks:[] };
  const data = goal.data;
  return { title:data.title, description:data.description, deadline:data.deadline ?? '', weekly_budget_minutes:String(data.weekly_budget_minutes), priority:data.priority, load_category:data.load_category, allowed_adjustment:data.allowed_adjustment, paused:data.paused, subtasks:data.subtasks.map(s=>({...s, estimated_minutes:String(s.estimated_minutes),task_id:s.task_id ?? ''})) };
}

export function goalPayload(revision:number, form:GoalForm): GoalWrite & GoalValues {
  function minutes(raw:string, max:number) {
    if (!/^\d+$/.test(raw) || Number(raw) > max) throw new Error(`请填写 0 至 ${max} 的整数分钟；每周预算必须明确填写。`);
    return Number(raw);
  }
  if (!form.title.trim()) throw new Error('请填写目标名称。');
  if (form.deadline && (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(form.deadline) || !Number.isFinite(Date.parse(form.deadline)))) throw new Error('截止时间需带时区，例如 2026-12-01T18:00:00+08:00；未知可留空。');
  return {revision, title:form.title.trim(), description:form.description, deadline:form.deadline || null,
    weekly_budget_minutes:minutes(form.weekly_budget_minutes,10080), priority:form.priority, load_category:form.load_category, allowed_adjustment:form.allowed_adjustment, paused:form.paused,
    subtasks:form.subtasks.map(s=>{if (!s.title.trim()) throw new Error('请填写子任务名称。'); return {...s,title:s.title.trim(),estimated_minutes:minutes(s.estimated_minutes,100000),task_id:s.task_id || null};})};
}

export function goalOperation(path:string, method:'POST'|'PATCH', body:GoalWrite): GoalOperation {
  return {path,method,body:structuredClone(body),idempotencyKey:crypto.randomUUID()};
}


export type SharedGoalCapacity = {
  contract_version: 'goal-capacity-v1'; status: 'known' | 'unknown'; week_start: string; week_end: string; timezone: string;
  source_revision: number; shared_capacity_upper_bound_minutes: number | null; active_weekly_budget_minutes: number;
  minimum_deficit_minutes: number | null; active_goal_ids: string[]; paused_goal_ids: string[]; goal_revisions: Record<string, number>;
  actual_minutes: null; capacity: {warnings: string[]; unknown_estimate_count: number} | null;
};

export function nextGoalCapacityWeek(timezone: string, now = new Date()) {
  const monday = new Date(currentReviewWeek(timezone, now) + 'T12:00:00Z');
  monday.setUTCDate(monday.getUTCDate() + 7);
  return monday.toISOString().slice(0, 10);
}

export function goalCapacityPath(week: string, timezone: string, sourceRevision: number) {
  if (mondayOf(week) !== week) throw new Error('容量范围需要从周一开始');
  new Intl.DateTimeFormat('zh-CN', {timeZone: timezone}).format();
  return `/goal-capacity?week_start=${week}&timezone=${encodeURIComponent(timezone)}&expected_source_revision=${sourceRevision}`;
}
