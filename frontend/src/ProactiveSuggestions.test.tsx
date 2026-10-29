import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { ProactiveSettings, ProactiveSuggestions } from './ProactiveSuggestions';
import type { ProactivePreferenceView } from './proactive-state';
const preferences:ProactivePreferenceView={id:null,kind:'proactive_preferences',revision:0,contract_version:'proactive-v1',data:{enabled:false,categories:{deadline:true,capacity:true,unknown_estimate:true,available_window:true,facts_changed:true},timezone:null,quiet_hours:null}};
function render(component:typeof ProactiveSettings|typeof ProactiveSuggestions,enabled=false) {
  const q=new QueryClient({defaultOptions:{queries:{retry:false}}});
  const saved=structuredClone(preferences);saved.data.enabled=enabled;
  q.setQueryData(['proactive','preferences'],saved);
  q.setQueryData(['proactive','suggestions'],{preferences:saved,suppression:enabled?null:'disabled',source_revision:5,capacity:null,suggestions:[{id:'s1',kind:'proactive_suggestion',revision:1,data:{title:'有依据的20分钟学习空档',category:'available_window',fingerprint:'f'.repeat(64),state:'pending',visible:enabled,reasons:['已确认学习窗口有20分钟','存在待完成步骤'],gaps:['实际投入未知'],sources:[{id:'task-source',kind:'task',revision:2}],task_id:'task-source',evidence:{},rank:30,first_seen_at:'2026-10-29T01:00:00Z',snoozed_until:null,resolved_at:null,source_revision:5}}]});
  const html=renderToStaticMarkup(createElement(QueryClientProvider,{client:q},createElement(component)));
  q.clear();return html;
}
it('shows explicit disabled defaults, unknown quiet preferences and accessible editing',()=>{
  const html=render(ProactiveSettings);
  expect(html).toContain('主动建议设置');expect(html).toContain('已关闭');expect(html).toContain('安静时段未知');expect(html).toContain('编辑主动建议设置');
});
it('shows silence and refresh while disabled without displaying candidate cards',()=>{
  const html=render(ProactiveSuggestions);
  expect(html).toContain('应用内无声');expect(html).toContain('刷新建议');expect(html).not.toContain('有依据的20分钟学习空档');
});
it('explains current evidence and exposes snooze, dismiss, category disable and original draft action',()=>{
  const html=render(ProactiveSuggestions,true);
  expect(html).toContain('有依据的20分钟学习空档');expect(html).toContain('实际投入未知');expect(html).toContain('task-source');expect(html).toContain('稍后30分钟');expect(html).toContain('关闭本条');expect(html).toContain('关闭此类建议');expect(html).toContain('生成待确认计划草稿');
});
