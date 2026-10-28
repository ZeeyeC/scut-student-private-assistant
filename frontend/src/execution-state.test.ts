import { describe, expect, it } from "vitest";
import { executionDisplay, newExecutionOperation } from "./execution-state";

describe("execution observations", () => {
  it("distinguishes missing, explicit zero and estimates", () => {
    expect(executionDisplay({ actual_minutes: null, legacy_estimated_minutes: 60 }).actualLabel).toBe("实际投入：未知");
    expect(executionDisplay({ actual_minutes: 0, legacy_estimated_minutes: 0 }).actualLabel).toBe("已记录实际：0 分钟");
    expect(executionDisplay({ actual_minutes: 25, legacy_estimated_minutes: 60 }).estimateLabel).toBe("另有历史估算：60 分钟");
    expect(executionDisplay({ actual_minutes: 25, legacy_estimated_minutes: 0 }).estimateLabel).toBeNull();
  });

  it("retains the body and idempotency key after a response is lost", () => {
    const original = { actual_minutes: 25 };
    const operation = newExecutionOperation("/executions", original);
    original.actual_minutes = 60;
    expect(operation.body.actual_minutes).toBe(25);
    expect(operation.idempotencyKey.length).toBeGreaterThan(0);
    expect(newExecutionOperation("/executions", original).executionId).not.toBe(operation.executionId);
  });
});
