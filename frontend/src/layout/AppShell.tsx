import type { ReactNode } from 'react';
import { CalendarDays, CircleCheck, House, MessageSquare, SlidersHorizontal } from 'lucide-react';
import type { PageId, NavigationTarget } from './navigation';

const entries = [
  {id:'today',label:'今日',icon:House}, {id:'calendar',label:'日程',icon:CalendarDays},
  {id:'tasks',label:'任务',icon:CircleCheck}, {id:'assistant',label:'助手',icon:MessageSquare},
] as const;
export function AppShell({page,onNavigate,children,footer}:{page:PageId;onNavigate:(target:NavigationTarget)=>void;children:ReactNode;footer?:ReactNode}) {
  const settings = <button type="button" aria-label="设置" data-page-id="settings" aria-current={page==='settings'?'page':undefined} onClick={()=>onNavigate({page:'settings'})}><SlidersHorizontal size={16}/><span>设置</span></button>;
  return <div className="shell workspace-shell">
    <aside className="workspace-sidebar">
      <div className="brand">课间<i className="workspace-brand-dot" aria-hidden="true"/></div>
      <nav aria-label="主导航">{entries.map(({id,label,icon:Icon})=><button type="button" aria-label={label} key={id} data-page-id={id} aria-current={page===id?'page':undefined} onClick={()=>onNavigate({page:id})}><Icon size={18}/><span>{label}</span></button>)}</nav>
      <div className="workspace-sidebar-bottom">{settings}{footer||<small className="workspace-local-status"><i aria-hidden="true"/>本机</small>}</div>
    </aside>
    <main id="workspace-content" className={page==='assistant'?'assistant-main':undefined}>{children}</main>
  </div>;
}
