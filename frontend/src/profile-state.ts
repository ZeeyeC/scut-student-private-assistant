export type ProfileWindow = { weekdays: number[]; start: string; end: string };
export type StudyWindow = ProfileWindow & { task_type: "any" | "deep" | "review" };
export type EnergyWindow = ProfileWindow & { level: "low" | "medium" | "high" };
export type ProfilePreferences = {
  preferred_study_windows: StudyWindow[] | null;
  energy_windows: EnergyWindow[] | null;
  focus_minutes: number | null;
  break_minutes: number | null;
  review_interval_days: number | null;
  daily_load_minutes: number | null;
  leisure_protection: "prefer_protect" | "flexible" | null;
};
export type ProfileInput = { timezone: string; effective_from: string | null; effective_until: string | null; preferences: ProfilePreferences };
export type StudyWindowDraft = Omit<StudyWindow, "task_type"> & { task_type: StudyWindow["task_type"] | "" };
export type EnergyWindowDraft = Omit<EnergyWindow, "level"> & { level: EnergyWindow["level"] | "" };
export type ProfileView = {
  id: string | null; kind: "user_profile"; revision: number; source_revision: number; contract_version: "profile-v1"; suggestions: Record<string, unknown>[];
  data: Omit<ProfileInput, "timezone"> & { timezone: string | null; schema_version: 1; source: "unknown" | "user"; confirmed: boolean; sample_count: 0; updated_at: string | null };
};
export type ProfileForm = Omit<ProfileInput, "preferences" | "effective_from" | "effective_until"> & Omit<ProfilePreferences, "focus_minutes" | "break_minutes" | "review_interval_days" | "daily_load_minutes" | "preferred_study_windows" | "energy_windows"> & {
  preferred_study_windows: StudyWindowDraft[] | null; energy_windows: EnergyWindowDraft[] | null;
  effective_from: string; effective_until: string; focus_minutes: string; break_minutes: string; review_interval_days: string; daily_load_minutes: string;
};
export type ProfileWrite = { revision: number; data: ProfileInput };
export type ProfileOperation = { method: "PUT" | "POST"; path: string; body: { revision: number; data?: ProfileInput }; idempotencyKey: string };
export function profileForm(profile: ProfileView): ProfileForm {
  const data = structuredClone(profile.data);
  const p = data.preferences;
  return {
    ...p, timezone: data.timezone ?? "", effective_from: data.effective_from ?? "", effective_until: data.effective_until ?? "",
    preferred_study_windows: p.preferred_study_windows?.map(w => ({ ...w, start: w.start.slice(0, 5), end: w.end.slice(0, 5) })) ?? null,
    energy_windows: p.energy_windows?.map(w => ({ ...w, start: w.start.slice(0, 5), end: w.end.slice(0, 5) })) ?? null,
    focus_minutes: p.focus_minutes === null ? "" : String(p.focus_minutes),
    break_minutes: p.break_minutes === null ? "" : String(p.break_minutes),
    review_interval_days: p.review_interval_days === null ? "" : String(p.review_interval_days),
    daily_load_minutes: p.daily_load_minutes === null ? "" : String(p.daily_load_minutes),
  };
}

export function profilePayload(revision: number, form: ProfileForm): ProfileWrite {
  try { new Intl.DateTimeFormat("zh-CN", { timeZone: form.timezone }).format(); }
  catch { throw new Error("请填写有效的 IANA 时区，例如 Asia/Shanghai。"); }
  if (!form.timezone.trim()) throw new Error("请明确填写时区。");
  if (form.effective_from && form.effective_until && form.effective_from > form.effective_until) throw new Error("有效截止日期不能早于起始日期。");
  function minutes(value: string, label: string, min: number, max: number) {
    if (!value.trim()) return null;
    const n = Number(value);
    if (!/^\d+$/.test(value) || !Number.isInteger(n) || n < min || n > max) throw new Error(`${label}需要 ${min} 至 ${max} 的整数；留空表示未知。`);
    return n;
  }
  for (const windows of [form.preferred_study_windows, form.energy_windows]) {
    for (const w of windows ?? []) {
      if (!w.weekdays.length || w.weekdays.some(d => !Number.isInteger(d) || d < 1 || d > 7) || new Set(w.weekdays).size !== w.weekdays.length || !/^([01]\d|2[0-3]):[0-5]\d$/.test(w.start) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(w.end) || w.start >= w.end) throw new Error("每个时段需选择星期和有效起止时间；跨午夜请拆开填写。");
    }
  }
  if (form.preferred_study_windows?.some(w => !["any", "deep", "review"].includes(w.task_type)) || form.energy_windows?.some(w => !["low", "medium", "high"].includes(w.level))) throw new Error("请明确选择学习类型或精力水平。");
  return {
    revision,
    data: {
      timezone: form.timezone, effective_from: form.effective_from || null, effective_until: form.effective_until || null,
      preferences: {
        preferred_study_windows: structuredClone(form.preferred_study_windows) as StudyWindow[] | null, energy_windows: structuredClone(form.energy_windows) as EnergyWindow[] | null,
        focus_minutes: minutes(form.focus_minutes, "专注时长", 5, 240), break_minutes: minutes(form.break_minutes, "休息时长", 0, 120),
        review_interval_days: minutes(form.review_interval_days, "复习间隔", 1, 365), daily_load_minutes: minutes(form.daily_load_minutes, "每天偏好负荷", 0, 720),
        leisure_protection: form.leisure_protection,
      },
    },
  };
}

export function newProfileOperation(method: "PUT" | "POST", path: string, body: ProfileOperation["body"]): ProfileOperation {
  return { method, path, body: structuredClone(body), idempotencyKey: crypto.randomUUID() };
}
