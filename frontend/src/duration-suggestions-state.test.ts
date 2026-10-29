import { expect, it } from 'vitest';
import { durationOperation, durationActions, type DurationSuggestion } from './duration-suggestions-state';
export const item:DurationSuggestion = {
  id:'suggestion',kind:'duration_suggestion',revision:1,freshness:'fresh',freshness_reason:null,current_task_revision:2,current_step_revision:3,current_source_revision:8,current_estimated_minutes:30,task_title:'作业',step_title:'阅读',
  data:{schema_version:1,source:'duration_generator',task_id:'task',task_revision:2,step_id:'step',step_revision:3,source_revision:8,default_estimated_minutes:30,suggested_minutes:45,reasons:['真实执行比预计更长'],sample_basis:[{execution_id:'record',execution_revision:1,actual_minutes:45,feedback:'completed'}],state:'pending',applied_step_revision:null,applied_source_revision:null},
};
it('captures real target/source revisions and preserves exact retry request',()=>{
  const row=structuredClone(item);
  const op=durationOperation(row,'accept');
  row.current_step_revision=99;row.data.suggested_minutes=99;
  expect(op.path).toBe('/duration-suggestions/suggestion/actions');
  expect(op.body).toEqual({revision:1,task_revision:2,step_revision:3,source_revision:8,action:'accept'});
  expect(op.idempotencyKey).toBeTruthy();
  expect(durationOperation(item,'reject').idempotencyKey).not.toBe(op.idempotencyKey);
});
it('only offers explicit valid actions and never applies stale advice',()=>{
  expect(durationActions(item)).toEqual(['accept','reject']);
  expect(()=>durationOperation(item,'restore_default')).toThrow();
  const accepted=structuredClone(item);accepted.data.state='accepted';accepted.current_step_revision=4;accepted.current_source_revision=9;
  expect(durationActions(accepted)).toEqual(['restore_default']);
  expect(durationOperation(accepted,'restore_default').body).toMatchObject({step_revision:4,source_revision:9,action:'restore_default'});
  accepted.freshness='stale';
  expect(durationActions(accepted)).toEqual([]);
  expect(()=>durationOperation(accepted,'restore_default')).toThrow();
});
