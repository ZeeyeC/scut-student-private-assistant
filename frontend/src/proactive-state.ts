import type { Resource } from './types';
export const proactiveCategories={deadline:'截止与未排风险',capacity:'容量不足',unknown_estimate:'预计耗时待补充',available_window:'真实学习空档',facts_changed:'事实变化后校对'} as const;
export type ProactiveCategory=keyof typeof proactiveCategories;
export type QuietWindow={weekdays:number[];start:string;end:string};
export type ProactivePreferences={enabled:boolean;categories:Record<ProactiveCategory,boolean>;timezone:string|null;quiet_hours:QuietWindow[]|null};
export type ProactivePreferenceView={id:string|null;kind:'proactive_preferences';revision:number;contract_version:'proactive-v1';data:ProactivePreferences};
export type ProactiveSuggestion={id:string;kind:'proactive_suggestion';revision:number;data:{category:ProactiveCategory;issue_key:string;fingerprint:string;title:string;reasons:string[];gaps:string[];rank:number;state:'pending'|'snoozed'|'dismissed'|'accepted'|'resolved'|'superseded';first_seen_at:string;snoozed_until:string|null;resolved_at:string|null;source_revision:number;sources:{id:string;kind:string;revision:number}[];evidence:Record<string,unknown>;task_id:string|null;visible:boolean}};
export type ProactiveList={contract_version:'proactive-v1';preferences:ProactivePreferenceView;suggestions:ProactiveSuggestion[];suppression:'disabled'|'inactive'|'quiet_hours'|null;source_revision:number|null;capacity:{capacity_upper_bound_minutes:number;required_minutes:number;unallocated_minutes:number;unknown_estimate_count:number;timezone:string}|null};
export type ProactiveOperation={method:'PUT'|'POST';path:string;body:Record<string,unknown>;idempotencyKey:string};
export type ProactiveActionResult={suggestion:ProactiveSuggestion;open_task_id:string|null;draft:Resource|null;requires_confirmation:boolean};
export type ProactiveAction='snooze'|'dismiss'|'disable_category'|'accept';

export function proactivePreferencePayload(revision:number,data:ProactivePreferences) {
  if(data.timezone!==null) {
    if(!data.timezone.trim()) throw new Error('请填写明确时区，未知可留空。');
    try {new Intl.DateTimeFormat('zh-CN',{timeZone:data.timezone}).format();}
    catch {throw new Error('请输入有效 IANA 时区，例如 Asia/Shanghai。');}
  }
  if(data.quiet_hours?.length&&!data.timezone) throw new Error('安静时段需要明确时区。');
  for(const window of data.quiet_hours??[]) {
    if(!window.weekdays.length||window.weekdays.some(d=>!Number.isInteger(d)||d<1||d>7)||new Set(window.weekdays).size!==window.weekdays.length||!/^([01]\d|2[0-3]):[0-5]\d$/.test(window.start)||!/^([01]\d|2[0-3]):[0-5]\d$/.test(window.end)||window.start===window.end) throw new Error('请选择星期并填写不同的起止时间；跨午夜按开始的星期计算。');
  }
  return {revision,data:structuredClone(data)};
}
export function proactiveOperation(method:'PUT'|'POST',path:string,body:Record<string,unknown>):ProactiveOperation {
  return {method,path,body:structuredClone(body),idempotencyKey:crypto.randomUUID()};
}
export function proactiveActionOperation(item:ProactiveSuggestion,action:ProactiveAction,options:{snooze_minutes?:number;accept_mode?:'details'|'replan'}={}) {
  if(action==='snooze'&&(!Number.isInteger(options.snooze_minutes)||options.snooze_minutes!<1||options.snooze_minutes!>10080)) throw new Error('稍后分钟数需为1至10080的整数。');
  if(action==='accept'&&!options.accept_mode) throw new Error('请明确选择打开详情或生成待确认草稿。');
  return proactiveOperation('POST',`/proactive/suggestions/${item.id}/actions`,{revision:item.revision,fingerprint:item.data.fingerprint,action,...options});
}
export function visibleProactive(items:ProactiveSuggestion[],appActive:boolean) {
  return appActive?items.filter(item=>item.data.visible&&item.data.state==='pending'):[];
}
