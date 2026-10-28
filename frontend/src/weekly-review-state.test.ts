import { describe, expect, it } from "vitest";
import { currentReviewWeek, mondayOf, reviewActionOperation, secondsLabel } from "./weekly-review-state";

describe("weekly review calendar and durable intent", () => {
  it("uses saved local day rather than browser or UTC week at a year boundary", () => {
    const instant = new Date("2027-01-03T16:30:00Z");
    expect(currentReviewWeek("Asia/Shanghai", instant)).toBe("2027-01-04");
    expect(currentReviewWeek("UTC", instant)).toBe("2026-12-28");
    expect(mondayOf("2027-01-03")).toBe("2026-12-28");
  });
  it("keeps unknown, zero and exact seconds visibly distinct", () => {
    expect(secondsLabel(null)).toContain("未知");
    expect(secondsLabel(0)).toBe("0 分钟");
    expect(secondsLabel(118)).toBe("1 分 58 秒");
  });
  it("captures source versions and reason and rejects acceptance without an intent", () => {
    expect(() => reviewActionOperation("2026-10-26", "Asia/Shanghai", 2, 7, "accept", " ")).toThrow();
    const operation = reviewActionOperation("2026-10-26", "Asia/Shanghai", 2, 7, "accept", " 前移学习时间 ");
    expect(operation.body).toEqual({ week_start: "2026-10-26", timezone: "Asia/Shanghai", revision: 2, source_revision: 7, action: "accept", reason: "前移学习时间" });
    expect(operation.idempotencyKey).toBeTruthy();
    expect(() => mondayOf("2026-02-30")).toThrow();
  });
});
