import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { Goals } from './Goals';
import { nextGoalCapacityWeek } from './goal-state';

function render(known: boolean) {
  const q = new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}});
  const week = nextGoalCapacityWeek('Asia/Shanghai');
  q.setQueryData(['settings'], {data:{timezone:'Asia/Shanghai'}});
  q.setQueryData(['goals'], {contract_version:'goals-v1', source_revision:2, capacity:{status:'unknown',weekly_available_minutes:null,integration_status:'pending'}, goals:[{
    id:'goal-1',revision:1,source_revision:2,contract_version:'goals-v1',references:[],arrangements:[],
    data:{title:'英语',description:'每周阅读',deadline:null,weekly_budget_minutes:0,priority:2,load_category:'study',allowed_adjustment:'ask',paused:true,subtasks:[],source:'user',confirmed:true,
      completion_history:[{subtask_id:'s1',title:'已完成第一章',estimated_minutes:20,task_id:null,completed_at:'2026-10-28T01:00:00Z',goal_revision:1}]}
  }]});
  q.setQueryData(['goal-capacity',week,'Asia/Shanghai',2], {contract_version:'goal-capacity-v1',status:known?'known':'unknown',week_start:week,week_end:'2026-11-09',timezone:'Asia/Shanghai',source_revision:2,shared_capacity_upper_bound_minutes:known?360:null,active_weekly_budget_minutes:known?600:0,minimum_deficit_minutes:known?240:null,active_goal_ids:known?['g2','g3']:[],paused_goal_ids:['goal-1'],goal_revisions:{'goal-1':1},actual_minutes:null,capacity:known?{warnings:[],unknown_estimate_count:1}:null});
  const html = renderToStaticMarkup(createElement(QueryClientProvider,{client:q},createElement(Goals)));
  q.clear();
  return html;
}

it('keeps unknown capacity distinct from zero and preserves paused completion facts', () => {
  const html = render(false);
  expect(html).toContain('未知（尚缺排程设置）');
  expect(html).toContain('已暂停');
  expect(html).toContain('恢复目标');
  expect(html).toContain('已完成第一章');
  expect(html).toContain('每周预算：0 分钟');
  expect(html).not.toContain('所有目标共享容量上限：0 分钟');
});

it('shows a single shared upper bound against the active total with unknown actual effort', () => {
  const html = render(true);
  expect(html).toContain('所有目标共享容量上限：360 分钟');
  expect(html).toContain('进行中目标每周预算合计：600 分钟');
  expect(html).toContain('至少缺口：240 分钟');
  expect(html.match(/360 分钟/g)).toHaveLength(1);
  expect(html).toContain('每个目标不会各自获得这一份时间');
  expect(html).toContain('目标实际投入与剩余预算未知');
  expect(html).toContain('有 1 项任务缺少耗时估计');
});
