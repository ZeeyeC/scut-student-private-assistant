export type DurationAction='accept'|'reject'|'restore_default';
export type DurationSuggestion={
  id:string;kind:'duration_suggestion';revision:number;freshness:'fresh'|'stale';freshness_reason:string|null;
  current_task_revision:number|null;current_step_revision:number|null;current_source_revision:number;
  current_estimated_minutes:number|null;task_title:string|null;step_title:string|null;
  data:{schema_version:1;source:'duration_generator';task_id:string;task_revision:number;step_id:string;step_revision:number;source_revision:number;
    default_estimated_minutes:number|null;suggested_minutes:number;reasons:string[];
    sample_basis:{execution_id:string;execution_revision:number;actual_minutes:number;feedback:'partial'|'completed'|'not_started'|'skipped'}[];
    state:'pending'|'accepted'|'rejected'|'restored';applied_step_revision:number|null;applied_source_revision:number|null;
  };
};
export type DurationSuggestionList={contract_version:'duration-suggestions-v1';generation_status:'not_integrated'|'ready';source_revision:number;invalid_suggestion_count:number;suggestions:DurationSuggestion[]};
export type DurationOperation={path:string;method:'POST';idempotencyKey:string;body:{revision:number;task_revision:number;step_revision:number;source_revision:number;action:DurationAction}};

export function durationActions(item:DurationSuggestion):DurationAction[] {
  if(item.freshness!=='fresh'||item.current_task_revision===null||item.current_step_revision===null)return [];
  if(item.data.state==='pending')return ['accept','reject'];
  if(item.data.state==='accepted')return ['restore_default'];
  return [];
}
export function durationOperation(item:DurationSuggestion,action:DurationAction):DurationOperation {
  if(!durationActions(item).includes(action))throw new Error('建议版本或状态已变化，请刷新后重新校对。');
  return {path:`/duration-suggestions/${encodeURIComponent(item.id)}/actions`,method:'POST',idempotencyKey:crypto.randomUUID(),
    body:{revision:item.revision,task_revision:item.current_task_revision!,step_revision:item.current_step_revision!,source_revision:item.current_source_revision,action}};
}
