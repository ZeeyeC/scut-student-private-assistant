import { expect, it } from "vitest";
import { JSDOM } from "jsdom";
import { captureScutList } from "../lib/scut-list";

it("measured list structure handles inherited periods and excludes identity, class groups and pending selection", () => {
  const doc =
    new JSDOM(`<input type="password" value="private"><table id="kblist_table">
 <tr><td colspan="4"><div class="timetable_title"><h6 class="pull-left">2026-2027学年第1学期</h6>测试姓名的课表<h6 class="pull-right">学号：secret-id</h6></div></td></tr>
 <tr><td id="xq_rowspan_4" rowspan="3">星期四</td></tr>
 <tr><td id="jc_4-1-2" rowspan="2"><span class="festival">1-2</span></td><td><div class="timetable_con"><span class="title"><font color="blue">Data Structure</font></span><p><font>周数：1周,4-10周(双),11-15周(单)</font><font>校区:大学城校区 上课地点：A2304</font><font>教师 ：测试教师</font><font>教学班：(2026-2027-1)-045100166-02</font><font>教学班组成：private-group</font></p></div></td></tr>
 <tr><td><div class="timetable_con"><span class="title"><font color="blue">Data Structure</font></span><p><font>周数：2-3周,5-9周(单),12-16周(双)</font><font>校区:大学城校区 上课地点：实验室</font><font>教师 ：测试教师</font><font>教学班：(2026-2027-1)-045100166-02</font></p></div></td></tr>
 <tr><td id="jc_4-9-12"><span>9-12</span></td><td><div class="timetable_con"><span class="title"><font color="red">待筛选课程</font></span><p><font>周数：第8周</font></p></div></td></tr></table>`)
      .window.document;
  const result = captureScutList(doc);
  expect(result).toContain("Data Structure");
  expect(result).toContain("实验室");
  expect(result).not.toMatch(
    /测试姓名|secret-id|private-group|password|private|待筛选课程|href|id=/,
  );
  const out = new JSDOM(result).window.document;
  const rows = Array.from(out.querySelectorAll("tbody tr"));
  expect(rows).toHaveLength(2);
  expect(rows[1]!.children[1]!.textContent).toBe("4");
  expect(rows[1]!.children[3]!.textContent).toBe("1-2");
});
