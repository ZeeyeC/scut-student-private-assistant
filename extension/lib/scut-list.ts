import { sanitizeTable } from "./extract";

// Measured 2026-10-14 at the student's real undergraduate list view.
// Normalize only confirmed course meetings; never copy title/name/student-id rows.
export function captureScutList(doc: Document): string {
  const source = doc.querySelector("#kblist_table");
  if (!source) throw new Error("尚未进入个人课表");
  const table = doc.createElement("table");
  table.innerHTML =
    "<thead><tr><th>课程</th><th>星期</th><th>周次</th><th>节次</th><th>地点</th><th>教师</th><th>校区</th><th>教学班</th></tr></thead>";
  const body = table.createTBody();
  let day = "",
    periods = "";
  for (const row of source.querySelectorAll("tr")) {
    const weekday = row.querySelector('td[id^="xq_rowspan_"]');
    if (weekday) {
      day = weekday.id.slice("xq_rowspan_".length);
      periods = "";
    }
    const period = row.querySelector('td[id^="jc_"]');
    if (period) {
      const match = /^jc_([1-7])-(\d+)-(\d+)$/.exec(period.id);
      if (!match) throw new Error("节次标记变化，需要重新核验");
      day = match[1]!;
      periods = match[2]! + "-" + match[3]!;
    }
    for (const meeting of row.querySelectorAll(".timetable_con")) {
      const title = meeting
        .querySelector('.title font[color="blue"]')
        ?.textContent?.trim();
      if (!title) continue; // Red/italic pending selections are not enrolled courses.
      if (!day || !periods) throw new Error("缺少星期或节次上下文");
      const fields = Array.from(meeting.querySelectorAll("p font")).map(
        (x) => x.textContent?.trim() ?? "",
      );
      const weeks = fields
        .find((x) => /^周数\s*[:：]/.test(x))
        ?.replace(/^周数\s*[:：]\s*/, "");
      const place = fields
        .find((x) => /^校区\s*[:：]/.test(x))
        ?.match(/^校区\s*[:：]\s*(.*?)\s*上课地点\s*[:：]\s*(.*)$/);
      const teacher =
        fields
          .find((x) => /^教师\s*[:：]/.test(x))
          ?.replace(/^教师\s*[:：]\s*/, "") ?? "";
      const classId =
        fields
          .find((x) => /^教学班\s*[:：]/.test(x))
          ?.replace(/^教学班\s*[:：]\s*/, "") ?? "";
      if (!weeks) throw new Error("周次结构变化，需要重新核验");
      const out = body.insertRow();
      for (const value of [
        title,
        day,
        weeks,
        periods,
        place?.[2] ?? "",
        teacher,
        place?.[1] ?? "",
        classId,
      ])
        out.insertCell().textContent = value;
    }
  }
  if (!body.rows.length) throw new Error("没有已选课程，请查询正确学期");
  return sanitizeTable(doc, table);
}
