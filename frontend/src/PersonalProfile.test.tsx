import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it } from "vitest";
import { PersonalProfile } from "./PersonalProfile";

function render(source: "unknown" | "user") {
  const q = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  q.setQueryData(["personal-profile"], {
    id: null, kind: "user_profile", revision: 0, source_revision: 0, contract_version: "profile-v1", suggestions: [],
    data: { schema_version: 1, timezone: null, effective_from: null, effective_until: null, source, confirmed: source === "user", sample_count: 0, updated_at: null,
      preferences: { preferred_study_windows: null, energy_windows: null, focus_minutes: null, break_minutes: null, review_interval_days: null, daily_load_minutes: null, leisure_protection: null } },
  });
  const html = renderToStaticMarkup(createElement(QueryClientProvider, { client: q }, createElement(PersonalProfile)));
  q.clear();
  return html;
}

it("shows unknown preferences and missing samples without claiming inferred habits", () => {
  const html = render("unknown");
  expect(html).toContain("尚未设置");
  expect(html).toContain("未知（未设置）");
  expect(html).toContain("执行样本：0");
  expect(html).toContain("目前仅保存偏好");
  expect(html).toContain("编辑偏好");
});

it("labels explicit user confirmation independently of unknown field values", () => {
  const html = render("user");
  expect(html).toContain("用户设置 · 已确认");
  expect(html).toContain("未知（未设置）");
  expect(html).toContain("暂无系统建议");
});
