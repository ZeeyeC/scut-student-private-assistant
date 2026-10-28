import { describe, expect, it } from "vitest";
import { profileForm, profilePayload, newProfileOperation, type ProfileView } from "./profile-state";

const profile: ProfileView = {
  id: null, kind: "user_profile", revision: 0, source_revision: 0, contract_version: "profile-v1", suggestions: [],
  data: { schema_version: 1, timezone: null, effective_from: null, effective_until: null, source: "unknown", confirmed: false, sample_count: 0, updated_at: null,
    preferences: { preferred_study_windows: null, energy_windows: null, focus_minutes: null, break_minutes: null, review_interval_days: null, daily_load_minutes: null, leisure_protection: null } },
};

describe("explicit profile editor", () => {
  it("does not turn missing preferences into habits or zero", () => {
    const form = profileForm(profile);
    expect(form.timezone).toBe("");
    expect(form.focus_minutes).toBe("");
    expect(form.preferred_study_windows).toBeNull();
    form.timezone = "Asia/Shanghai";
    const payload = profilePayload(0, form);
    expect(payload.data.preferences.focus_minutes).toBeNull();
    expect(payload.data.preferences.break_minutes).toBeNull();
    expect(payload.data.preferences.preferred_study_windows).toBeNull();
    expect(payload.data.effective_from).toBeNull();
  });

  it("preserves explicit zero, explicit empty windows and a user-selected deep study window", () => {
    const form = profileForm(profile);
    Object.assign(form, { timezone: "Asia/Shanghai", break_minutes: "0", daily_load_minutes: "0", preferred_study_windows: [], energy_windows: [{ weekdays: [1], start: "19:00", end: "21:00", level: "high" }] });
    const payload = profilePayload(3, form);
    expect(payload.revision).toBe(3);
    expect(payload.data.preferences.daily_load_minutes).toBe(0);
    expect(payload.data.preferences.break_minutes).toBe(0);
    expect(payload.data.preferences.preferred_study_windows).toEqual([]);
    form.preferred_study_windows = [{ weekdays: [1], start: "19:00", end: "21:00", task_type: "deep" }];
    expect(profilePayload(3, form).data.preferences.preferred_study_windows?.[0].task_type).toBe("deep");
  });

  it("keeps editable values separate from the persisted profile", () => {
    const saved = structuredClone(profile);
    saved.data.timezone = "Asia/Shanghai";
    saved.data.preferences.preferred_study_windows = [{ weekdays: [1], start: "19:00:00", end: "21:00:00", task_type: "deep" }];
    const form = profileForm(saved);
    expect(form.preferred_study_windows?.[0].start).toBe("19:00");
    form.preferred_study_windows![0].weekdays.push(2);
    expect(saved.data.preferences.preferred_study_windows[0].weekdays).toEqual([1]);
  });

  it.each([
    { timezone: "Bad/Zone" }, { focus_minutes: "4" }, { focus_minutes: "45.5" },
    { break_minutes: "-1" }, { daily_load_minutes: "721" }, { review_interval_days: "0" },
    { effective_from: "2026-12-01", effective_until: "2026-11-01" },
    { preferred_study_windows: [{ weekdays: [], start: "19:00", end: "21:00", task_type: "deep" }] },
    { energy_windows: [{ weekdays: [1], start: "21:00", end: "19:00", level: "high" }] },
    { energy_windows: [{ weekdays: [1], start: "19:00", end: "21:00", level: "" }] },
    { preferred_study_windows: [{ weekdays: [1], start: "19:00", end: "21:00", task_type: "" }] },
  ])("rejects malformed explicit input before sending: %j", change => {
    const form = Object.assign(profileForm(profile), { timezone: "Asia/Shanghai" }, change);
    expect(() => profilePayload(0, form)).toThrow();
  });

  it("freezes the exact write for retry after a lost response", () => {
    const form = profileForm(profile);
    form.timezone = "Asia/Shanghai";
    const payload = profilePayload(0, form);
    const operation = newProfileOperation("PUT", "/profile", payload);
    payload.data.preferences.focus_minutes = 60;
    expect(operation.body.data?.preferences.focus_minutes).toBeNull();
    expect(operation.idempotencyKey).toBeTruthy();
    expect(newProfileOperation("POST", "/profile/reset", { revision: 0 }).idempotencyKey).not.toBe(operation.idempotencyKey);
  });
});
