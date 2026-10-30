export type PageId = 'today' | 'calendar' | 'tasks' | 'assistant' | 'settings';
export type CalendarFilter = 'all' | 'courses' | 'study';
export type TaskTab = 'todo' | 'goals' | 'review';
export type NavigationTarget = {
  page: PageId; taskId?: string; focusDate?: string;
  calendarFilter?: CalendarFilter; taskTab?: TaskTab; threadId?: string;
};
export type NavigationState = NavigationTarget & { request: number };
const aliases: Record<string, NavigationTarget> = {
  '今日': {page:'today'}, '日程': {page:'calendar'},
  '课表': {page:'calendar',calendarFilter:'courses'},
  '作业': {page:'tasks'}, '任务': {page:'tasks'},
  '目标与复盘': {page:'tasks',taskTab:'goals'},
  '助手': {page:'assistant'}, '设置': {page:'settings'},
};
const pages: PageId[] = ['today','calendar','tasks','assistant','settings'];
const identifier = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0 && v.length <= 200 && !/[\r\n]/.test(v);
function date(v: unknown): v is string {
  if(typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(v) || !Number.isFinite(Date.parse(v))) return false;
  return new Date(v.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10) === v.slice(0,10);
}
function target(value: unknown): NavigationTarget | null {
  if(typeof value === 'string') return aliases[value] ? {...aliases[value]} : pages.includes(value as PageId) ? {page:value as PageId} : null;
  if(!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const v=value as Record<string, unknown>;
  if(!pages.includes(v.page as PageId)) return null;
  const result: NavigationTarget = {page:v.page as PageId};
  if(v.taskId !== undefined) { if(v.page !== 'tasks' || !identifier(v.taskId)) return null; result.taskId=v.taskId; }
  if(v.threadId !== undefined) { if(v.page !== 'assistant' || !identifier(v.threadId)) return null; result.threadId=v.threadId; }
  if(v.focusDate !== undefined) { if(v.page !== 'calendar' || !date(v.focusDate)) return null; result.focusDate=v.focusDate; }
  if(v.calendarFilter !== undefined) { if(v.page !== 'calendar' || !['all','courses','study'].includes(String(v.calendarFilter))) return null; result.calendarFilter=v.calendarFilter as CalendarFilter; }
  if(v.taskTab !== undefined) { if(v.page !== 'tasks' || !['todo','goals','review'].includes(String(v.taskTab))) return null; result.taskTab=v.taskTab as TaskTab; }
  return result;
}
export function navigationFromEvent(name: string, detail: unknown): NavigationTarget | null {
  if(name==='campus-navigate') return target(detail);
  if(name==='campus-calendar-saved' || name==='campus-timetable-focus') return date(detail) ? {page:'calendar',focusDate:detail,calendarFilter:name==='campus-calendar-saved'?'all':'courses'} : null;
  if(name==='campus-pet-review') {
    const threadId=(detail as {threadId?:unknown}|null)?.threadId;
    return threadId===undefined || threadId===null ? {page:'assistant'} : identifier(threadId) ? {page:'assistant',threadId} : null;
  }
  return null;
}
export function nextNavigation(previous: NavigationState, value: NavigationTarget): NavigationState {
  return {...value,request:previous.request+1};
}
