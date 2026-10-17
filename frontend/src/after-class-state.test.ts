import { describe, it, expect } from "vitest";
import { draftAnswers, mergePendingAnswers } from "./after-class-state";

describe("after-class recovery", () => {
  it("keeps local input only for courses still pending in the latest record", () => {
    const local = ["a", "b"].map(course_key => ({ course_key, status: "homework" as const, items: [{ content: `local-${course_key}`, estimated_minutes: 45, due_at: "" }] }));
    const result = mergePendingAnswers([{ key: "b" }, { key: "c" }], [], local);
    expect(result.map(a => a.course_key)).toEqual(["b", "c"]);
    expect(result[0].items[0].content).toBe("local-b");
    expect(result[1].status).toBe("pending");
  });
  it("omits hidden invalid homework fields without changing visible homework", () => {
    const item = { content: "", estimated_minutes: 0, due_at: "invalid" };
    expect(draftAnswers(["none", "pending"].map(status => ({ course_key: status, status: status as "none" | "pending", items: [item] })))).toEqual([
      { course_key: "none", status: "none", items: [] }, { course_key: "pending", status: "pending", items: [] },
    ]);
    expect(draftAnswers([{ course_key: "b", status: "homework", items: [{ content: "retain", estimated_minutes: 45, due_at: "" }] }])[0].items).toEqual([{ content: "retain", estimated_minutes: 45, due_at: null }]);
  });
});
