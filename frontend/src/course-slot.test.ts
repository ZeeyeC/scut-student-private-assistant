import { describe, expect, it } from "vitest";
import { courseSlot } from "./course-slot";
import type { SettingsData } from "./types";

const settings: SettingsData = {
  timezone: "Asia/Shanghai", semester_name: "秋季", week1_monday: "2026-10-12", week_count: 20,
  periods: { "1": { start: "08:10", end: "08:55" }, "2": { start: "09:05", end: "09:50" } },
  daily_limit_minutes: 180, max_block_minutes: 60, min_block_minutes: 15, buffer_minutes: 10,
};

describe("blank timetable cell defaults", () => {
  it("uses the calendar date and timezone, including Sunday near midnight", () => {
    expect(courseSlot("2026-10-18T23:30:00-10:00", settings)).toMatchObject({weekday: 7, weeks: "1"});
    expect(courseSlot("2026-10-19T00:00:00+14:00", settings)).toMatchObject({weekday: 1, weeks: "2"});
  });
  it("matches an actual period inside a half-hour cell without inventing a school timetable", () => {
    expect(courseSlot("2026-10-15T08:00:00+08:00", settings)).toMatchObject({weekday: 4, weeks: "1", periods: "1", notice: ""});
    expect(courseSlot("2026-10-15T09:00:00+08:00", settings).periods).toBe("2");
    expect(courseSlot("2026-10-15T09:30:00+08:00", settings).periods).toBe("2");
    expect(courseSlot("2026-10-15T10:00:00+08:00", settings)).toMatchObject({periods: "", notice: expect.stringContaining("没有匹配")});
  });
  it("leaves unset and out-of-semester weeks blank for explicit user input", () => {
    expect(courseSlot("2026-10-11T09:00:00+08:00", settings)).toMatchObject({weeks: "", notice: expect.stringContaining("不在当前学期")});
    expect(courseSlot("2027-03-01T09:00:00+08:00", settings).weeks).toBe("");
    expect(courseSlot("2026-10-15T09:00:00+08:00")).toMatchObject({weekday: 4, weeks: "", periods: "", notice: expect.stringContaining("尚未设置")});
  });
});
