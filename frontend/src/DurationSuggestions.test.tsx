import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect,it } from 'vitest';
import { DurationSuggestions } from './DurationSuggestions';
import type { DurationSuggestion } from './duration-suggestions-state';
function render(suggestions:DurationSuggestion[],status:'not_integrated'|'ready'='not_integrated') {
  const q=new QueryClient();
  q.setQueryData(['duration-suggestions'],{contract_version:'duration-suggestions-v1',generation_status:status,source_revision:1,invalid_suggestion_count:0,suggestions});
  const html=renderToStaticMarkup(createElement(QueryClientProvider,{client:q},createElement(DurationSuggestions)));
  q.clear();return html;
}
it('honestly displays missing generation service without fabricated sample advice',()=>{
  const html=render([]);
  expect(html).toContain('未接入生成服务');expect(html).toContain('暂无可消费的有效时长建议');expect(html).not.toContain('接受此时长');
});
it('offers real generation only when the producer is ready and explains missing samples',()=>{
  const html=render([],'ready');
  expect(html).toContain('检查并生成时长建议');expect(html).toContain('至少 3 条真实执行');
  expect(html).toContain('样本不足');expect(html).not.toContain('未接入生成服务');
});
it('displays persisted reason/sample evidence, explicit actions and stale blocking',()=>{
  const item:DurationSuggestion={id:'x',kind:'duration_suggestion',revision:1,freshness:'fresh',freshness_reason:null,current_task_revision:1,current_step_revision:1,current_source_revision:1,current_estimated_minutes:30,task_title:'作业',step_title:'阅读',data:{schema_version:1,source:'duration_generator',task_id:'task',task_revision:1,step_id:'step',step_revision:1,source_revision:1,default_estimated_minutes:30,suggested_minutes:45,reasons:['已确认样本依据'],sample_basis:[{execution_id:'r',execution_revision:1,actual_minutes:45,feedback:'completed'}],state:'pending',applied_step_revision:null,applied_source_revision:null}};
  const html=render([item]);
  expect(html).toContain('已确认样本依据');expect(html).toContain('45 分钟');expect(html).toContain('接受此时长');expect(html).toContain('拒绝此建议');
  expect(html).toContain('实际 45 分钟');expect(html).toContain('执行记录 r');
  item.freshness='stale';item.freshness_reason='执行样本已更正';
  const stale=render([item]);expect(stale).toContain('执行样本已更正');expect(stale).not.toContain('接受此时长');
});
