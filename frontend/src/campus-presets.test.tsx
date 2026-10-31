import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { DraftReview } from "./DraftReview";
import { TimetableImportPanel } from "./TimetableImportPanel";
import { CAMPUS_PRESETS } from "./CampusPresetSelector";
import type { Resource } from "./types";

vi.mock("./layout/DetailPanel",()=>({DetailPanel:({children}:{children: import("react").ReactNode})=>createElement("section",null,children)}));

function makeClient(campusPreset: string | null = null) {
  const q = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  q.setQueryData(["settings"], {
    id: "s1",
    kind: "settings",
    revision: 1,
    data: {
      timezone: "Asia/Shanghai",
      semester_name: "2026秋季",
      week1_monday: "2026-09-07",
      week_count: 20,
      campus_preset: campusPreset,
      periods: {},
      study_windows: [],
      daily_limit_minutes: 180,
      max_block_minutes: 60,
      min_block_minutes: 15,
      buffer_minutes: 10,
      campus_transfers: [],
    },
  });
  q.setQueryData(["courses"], []);
  q.setQueryData(["drafts"], []);
  q.setQueryData(["browser-imports"], []);
  q.setQueryData(["timetable-jobs"], []);
  q.setQueryData(["campus-presets"], CAMPUS_PRESETS);
  return q;
}

it("never renders campus preset selector or time inputs on the empty import screen", () => {
  const q = makeClient();
  const html = renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: q },
      createElement(TimetableImportPanel, { open: true, onClose: () => {} }),
    ),
  );
  expect(html).toContain("从学校导入");
  expect(html).not.toContain("校区节次模板");
  expect(html).not.toContain('type="time"');
  q.clear();
});

it("renders selector in school timetable review after summary and before replace checkbox and course fields without time inputs", () => {
  const q = makeClient("wushan");
  const draft: Resource = {
    id: "d-school",
    kind: "draft",
    revision: 1,
    data: {
      draft_kind: "timetable",
      status: "pending",
      changes: { added: ["c1"], changed: [], possibly_removed: [] },
      payload: {
        save_mode: "merge",
        completeness: "partial",
        semester_label: "2026秋季",
        warnings: [],
        courses: [
          {
            source_key: "c1",
            name: "数据结构",
            campus: "大学城",
            location: "A1-202",
            weekday: 1,
            weeks: [1, 2],
            periods: [1, 2],
          },
        ],
      },
    },
  };
  const html = renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: q },
      createElement(DraftReview, { draft }),
    ),
  );
  const summaryIdx = html.indexOf("1 门课程");
  const selectorIdx = html.indexOf("校区节次模板");
  const replaceIdx = html.indexOf("替换当前课表");
  const courseIdx = html.indexOf("数据结构");
  expect(summaryIdx).toBeGreaterThan(-1);
  expect(selectorIdx).toBeGreaterThan(summaryIdx);
  expect(replaceIdx).toBeGreaterThan(selectorIdx);
  expect(courseIdx).toBeGreaterThan(replaceIdx);
  expect(html).toContain("08:00-08:45");
  expect(html).toContain("21:35-22:00");
  expect(html).toContain("07:00");
  expect(html).toContain("09:40-10:00");
  expect(html).not.toContain('type="time"');

  const wushanOpt = html.indexOf(">五山<");
  const guojiOpt = html.indexOf(">国际<");
  const daxuechengOpt = html.indexOf(">大学城<");
  expect(wushanOpt).toBeGreaterThan(-1);
  expect(guojiOpt).toBeGreaterThan(wushanOpt);
  expect(daxuechengOpt).toBeGreaterThan(guojiOpt);
  q.clear();
});

it("renders selector in image/PDF and text timetable reviews before course candidates with readonly 12-period schedule", () => {
  for (const kind of ["timetable_recognition", "timetable_text"] as const) {
    const q = makeClient("guoji");
    q.setQueryData(["timetable-asset", "asset-1"], {
      id: "asset-1",
      kind: "asset",
      revision: 1,
      data: { pages: [{ number: 1, type: "image", text: "" }] },
    });
    const draft: Resource = {
      id: `d-${kind}`,
      kind: "draft",
      revision: 1,
      data: {
        draft_kind: kind,
        status: "pending",
        source:
          kind === "timetable_text"
            ? { messages: [{ run_id: "r1", text: "高等数学周一1,2节" }] }
            : { asset_id: "asset-1", page_count: 1 },
        payload: {
          semester_label: "2026秋季",
          semester_confirmed: true,
          warnings: [],
          candidates: [
            {
              candidate_id: "cand-1",
              name: "高等数学",
              teacher: null,
              campus: "五山",
              location: "3401",
              weekday: 1,
              weeks_text: "1-16周",
              periods: [1, 2],
              reviewed: true,
              excluded: false,
              uncertain_fields: [],
              evidence: [],
            },
          ],
        },
      },
    };
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client: q },
        createElement(DraftReview, { draft }),
      ),
    );
    const semesterConfirmIdx = html.indexOf("且与当前设置一致");
    const selectorIdx = html.indexOf("校区节次模板");
    const candidateIdx = html.indexOf("课程 1");
    expect(semesterConfirmIdx).toBeGreaterThan(-1);
    expect(selectorIdx).toBeGreaterThan(semesterConfirmIdx);
    expect(candidateIdx).toBeGreaterThan(selectorIdx);
    expect(html).toContain("08:50-09:35");
    expect(html).toContain("10:25-10:40");
    expect(html).not.toContain('type="time"');
    q.clear();
  }
});
