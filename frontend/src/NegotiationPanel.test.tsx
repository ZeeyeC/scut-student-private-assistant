import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {expect,it} from 'vitest';
import {NegotiationPanel} from './NegotiationPanel';

it('reads the chosen draft directly after confirmation instead of relying on the pending-only list',()=>{
  const q=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}});
  q.setQueryData(['me'],{id:'owner'});
  q.setQueryData(['settings'],{id:'s',kind:'settings',revision:2,data:{timezone:'Asia/Shanghai',daily_limit_minutes:180}});
  q.setQueryData(['plan-blocks'],[]);
  q.setQueryData(['drafts'],[]);
  q.setQueryData(['planning-intents'],[{id:'intent',kind:'planning_intent',revision:3,data:{status:'chosen',conditions:{description:'合成协商',target_date:'2026-11-04',horizon_days:1,timezone:'Asia/Shanghai',protected_intervals:[],preferred_intervals:[],keep_block_ids:[],reduced_daily_limit_minutes:null},preview:null,choice:{draft_id:'chosen-draft'}}}]);
  q.setQueryData(['negotiation-draft','chosen-draft'],{id:'chosen-draft',kind:'draft',revision:2,data:{status:'confirmed',draft_kind:'plan',payload:{}}});
  const html=renderToStaticMarkup(createElement(QueryClientProvider,{client:q},createElement(NegotiationPanel)));
  expect(html).toContain('所选计划草稿：已确认');
  expect(html).not.toContain('校对完成，准备保存');
  q.clear();
});
