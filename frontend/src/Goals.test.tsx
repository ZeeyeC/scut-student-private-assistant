import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { Goals } from './Goals';

it('shows user-confirmed goal, unknown capacity, retained completion facts and explicit resume', () => {
  const q = new QueryClient();
  q.setQueryData(['goals'], { contract_version: 'goals-v1', source_revision: 2, capacity: { status:'unknown', weekly_available_minutes:null, integration_status:'pending' }, goals: [{
    id:'goal-1', revision:1, source_revision:2, contract_version:'goals-v1', references:[], arrangements:[],
    data:{ title:'英语', description:'每周阅读', deadline:null, weekly_budget_minutes:0, priority:2, load_category:'study', allowed_adjustment:'ask', paused:true, subtasks:[], source:'user', confirmed:true,
      completion_history:[{subtask_id:'s1', title:'已完成第一章', estimated_minutes:20, task_id:null, completed_at:'2026-10-28T01:00:00Z', goal_revision:1}] }
  }] });
  const html = renderToStaticMarkup(createElement(QueryClientProvider, {client:q}, createElement(Goals)));
  expect(html).toContain('容量未知');
  expect(html).toContain('已暂停');
  expect(html).toContain('恢复目标');
  expect(html).toContain('已完成第一章');
  expect(html).toContain('0 分钟');
  expect(html).not.toContain('可用 0');
  q.clear();
});
