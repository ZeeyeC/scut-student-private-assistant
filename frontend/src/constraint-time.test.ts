import { describe, it, expect } from "vitest";
import { constraintInput, constraintInstant } from "./constraint-time";

describe("explicit constraint timezone", () => {
  it("uses the saved timezone rather than the computer timezone", () => {
    expect(constraintInstant("2026-10-14T14:00", "Asia/Shanghai")).toBe("2026-10-14T14:00:00.000+08:00");
    expect(constraintInput("2026-10-14T06:00:00Z", "Asia/Shanghai")).toBe("2026-10-14T14:00");
    expect(Date.parse(constraintInstant("2026-10-14T14:00", "America/New_York"))).toBe(Date.parse("2026-10-14T18:00:00Z"));
  });
  it("rejects skipped or ambiguous DST wall times", () => {
    expect(() => constraintInstant("2026-03-08T02:30", "America/New_York")).toThrow("跳过");
    expect(() => constraintInstant("2026-11-01T01:30", "America/New_York")).toThrow("两个同名时间");
    expect(() => constraintInstant("2026-10-14T14:00", "Invalid/zone")).toThrow();
  });
});
