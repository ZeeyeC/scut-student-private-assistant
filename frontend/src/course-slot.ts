import type { SettingsData } from "./types";

export type CourseSlot = {
  date: string;
  time: string;
  weekday: number;
  weeks: string;
  periods: string;
  notice: string;
};

/** FullCalendar supplies the date/time in the calendar's configured timezone. */
export function courseSlot(dateStr: string, settings?: SettingsData): CourseSlot {
  const date = dateStr.slice(0, 10);
  const time = dateStr.slice(11, 16);
  const day = Date.parse(`${date}T00:00:00Z`);
  const weekday = new Date(day).getUTCDay() || 7;
  const notices: string[] = [];
  let weeks = "";
  if (settings?.week1_monday) {
    const first = Date.parse(`${settings.week1_monday}T00:00:00Z`);
    const week = Math.floor((day - first) / (7 * 86400000)) + 1;
    if (week >= 1 && week <= settings.week_count) weeks = String(week);
    else notices.push("所选日期不在当前学期内，请核对周次或在设置中修改学期日期。");
  } else notices.push("尚未设置第一周周一，请填写周次，并在设置中补齐学期日期。");

  const minutes = (value: string) => {
    const [h, m] = value.split(":").map(Number);
    return h * 60 + m;
  };
  const at = minutes(time);
  const periods = Object.entries(settings?.periods ?? {}).sort(([a], [b]) => Number(a) - Number(b));
  // Prefer a period containing the click. Otherwise match a period that starts
  // within the clicked half-hour cell, rather than guessing across a break.
  let matched = periods.filter(([, p]) => minutes(p.start) <= at && at < minutes(p.end));
  if (!matched.length) matched = periods.filter(([, p]) => at <= minutes(p.start) && minutes(p.start) < at + 30);
  if (!matched.length) notices.push(periods.length
    ? "这个时间格没有匹配的上课节次，请手动填写节次。"
    : "尚未设置实际节次时间，请填写节次，并在设置中补齐对应时间。");
  return { date, time, weekday, weeks, periods: matched.map(([number]) => number).join(","), notice: notices.join(" ") };
}
