export type ExecutionSummary = {
  task_id: string;
  step_id: string | null;
  actual_minutes: number | null;
  actual_seconds?: number | null;
  unconfirmed_execution_ids?: string[];
  legacy_estimated_minutes: number;
  unresolved_legacy_minutes: number;
  planning_spent_minutes: number;
  unknown_step_ids: string[];
  effective_record_ids: string[];
  source_revision: number;
};

export function executionDisplay(summary: Pick<ExecutionSummary, "actual_minutes" | "legacy_estimated_minutes">) {
  return {
    actualLabel: summary.actual_minutes === null ? "实际投入：未知" : `已记录实际：${summary.actual_minutes} 分钟`,
    estimateLabel: summary.legacy_estimated_minutes > 0 ? `另有历史估算：${summary.legacy_estimated_minutes} 分钟` : null,
  };
}

export function newExecutionOperation<T extends object>(path: string, body: T) {
  return { path, body: structuredClone(body), executionId: crypto.randomUUID(), idempotencyKey: crypto.randomUUID() };
}

