import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { Button } from "./components/ui/button";
import { newProfileOperation, profileForm, profilePayload, type EnergyWindowDraft, type ProfileForm, type ProfileOperation, type ProfileView, type ProfileWindow, type StudyWindowDraft } from "./profile-state";

const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
const unknown = "未知（未设置）";
const taskLabels = { any: "任意学习", deep: "深度学习", review: "复习" };
const energyLabels = { high: "精力高", medium: "精力中等", low: "精力低" };

function windowLabel(w: ProfileWindow) {
  return `周${w.weekdays.map(d => weekdays[d - 1]).join("、")} ${w.start.slice(0, 5)}–${w.end.slice(0, 5)}`;
}

function WindowEditor<T extends StudyWindowDraft | EnergyWindowDraft>({ title, rows, onChange, energy }: { title: string; rows: T[] | null; onChange: (rows: T[] | null) => void; energy?: boolean }) {
  function patch(index: number, value: Partial<T>) {
    onChange(rows!.map((row, i) => i === index ? { ...row, ...value } : row));
  }
  return <fieldset>
    <legend>{title}</legend>
    <p>{rows === null ? unknown : rows.length ? "仅为偏好，不代替不可安排时段。" : "已明确不指定任何偏好时段。"}</p>
    {rows?.map((row, i) => <fieldset key={i}>
      <legend>{title} {i + 1}</legend>
      <div aria-label="适用星期">{weekdays.map((label, day) => <label key={day} style={{ display: "inline-block", marginRight: 12 }}>
        <input type="checkbox" checked={row.weekdays.includes(day + 1)} onChange={e => patch(i, { weekdays: e.target.checked ? [...row.weekdays, day + 1].sort() : row.weekdays.filter(d => d !== day + 1) } as Partial<T>)} />周{label}
      </label>)}</div>
      <div className="grid2">
        <label>开始时间<input type="time" step="60" value={row.start} onChange={e => patch(i, { start: e.target.value } as Partial<T>)} /></label>
        <label>结束时间<input type="time" step="60" value={row.end} onChange={e => patch(i, { end: e.target.value } as Partial<T>)} /></label>
        {energy ? <label>粗粒度精力<select value={(row as EnergyWindowDraft).level} onChange={e => patch(i, { level: e.target.value } as unknown as Partial<T>)}>
          <option value="">请选择精力水平</option>{Object.entries(energyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label> : <label>适合的学习类型<select value={(row as StudyWindowDraft).task_type} onChange={e => patch(i, { task_type: e.target.value } as unknown as Partial<T>)}>
          <option value="">请选择学习类型</option>{Object.entries(taskLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>}
      </div>
      <Button type="button" variant="outline" onClick={() => onChange(rows.filter((_, j) => i !== j))}>移除此时段</Button>
    </fieldset>)}
    <Button type="button" variant="outline" onClick={() => onChange([...(rows ?? []), { weekdays: [], start: "", end: "", ...(energy ? { level: "" } : { task_type: "" }) } as unknown as T])}>添加{title}</Button>
    {rows === null ? <Button type="button" variant="outline" onClick={() => onChange([])}>明确不指定时段</Button> : <Button type="button" variant="outline" onClick={() => onChange(null)}>恢复为未知</Button>}
  </fieldset>;
}

export function PersonalProfile() {
  const q = useQueryClient();
  const profile = useQuery({ queryKey: ["personal-profile"], queryFn: () => api<ProfileView>("/profile") });
  const [editor, setEditor] = useState<{ revision: number; form: ProfileForm } | null>(null);
  const [pending, setPending] = useState<ProfileOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const data = profile.data?.data;
  const p = data?.preferences;
  const locked = busy || !!pending;

  function change(values: Partial<ProfileForm>) {
    if (editor) setEditor({ ...editor, form: { ...editor.form, ...values } });
  }

  async function submit(reset = false) {
    if (busyRef.current) return;
    setError(""); setMessage("");
    let operation = pending;
    if (!operation) {
      try {
        if (reset && profile.data) operation = newProfileOperation("POST", "/profile/reset", { revision: profile.data.revision });
        else if (editor) operation = newProfileOperation("PUT", "/profile", profilePayload(editor.revision, editor.form));
        else return;
      } catch (e) { setError(String(e)); return; }
      setPending(operation);
    }
    busyRef.current = true; setBusy(true);
    try {
      const saved = await api<ProfileView>(operation.path, { method: operation.method, headers: { "Idempotency-Key": operation.idempotencyKey }, body: JSON.stringify(operation.body) });
      q.setQueryData(["personal-profile"], saved);
      setPending(null); setEditor(null); setResetConfirm(false);
      setMessage(operation.path.endsWith("/reset") ? "偏好已重置为未知，课程和任务保留。" : "用户确认的偏好已保存。排程联动仍待接入与对照验收。");
      await q.invalidateQueries();
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        setPending(null);
        if (e.status === 409) { setEditor(null); setResetConfirm(false); await q.invalidateQueries({ queryKey: ["personal-profile"] }); }
      }
      setError(String(e));
    } finally { busyRef.current = false; setBusy(false); }
  }

  return <section aria-label="用户偏好与精力档案">
    <h3>偏好与精力档案</h3>
    <p>目前仅保存偏好，排程联动仍待接入与对照验收。未设置的项目保持未知，现有计划规则继续适用。</p>
    {profile.isPending && <p role="status">正在读取档案…</p>}
    {profile.error && <><p role="alert">档案读取失败：{String(profile.error)}</p><Button type="button" variant="outline" disabled={locked} onClick={() => profile.refetch()}>重试读取档案</Button></>}
    {profile.data && data && p && <>
      <p>来源：{data.source === "user" && data.confirmed ? "用户设置 · 已确认" : "尚未设置"} · 执行样本：{data.sample_count}（当前未从执行记录推断习惯）</p>
      <p>时区：{data.timezone ?? unknown} · 有效日期：{data.effective_from ?? "未限定起始"} 至 {data.effective_until ?? "未限定截止"}（含当日）</p>
      <p>档案版本：{profile.data.revision}</p>
      <dl>
        <dt>偏好学习时段</dt><dd>{p.preferred_study_windows === null ? unknown : !p.preferred_study_windows.length ? "明确不指定时段" : p.preferred_study_windows.map((w, i) => <p key={i}>{windowLabel(w)} · {taskLabels[w.task_type]}</p>)}</dd>
        <dt>粗粒度精力时段</dt><dd>{p.energy_windows === null ? unknown : !p.energy_windows.length ? "明确不指定时段" : p.energy_windows.map((w, i) => <p key={i}>{windowLabel(w)} · {energyLabels[w.level]}</p>)}</dd>
        <dt>专注时长</dt><dd>{p.focus_minutes === null ? unknown : `${p.focus_minutes} 分钟`}</dd>
        <dt>休息时长</dt><dd>{p.break_minutes === null ? unknown : `${p.break_minutes} 分钟`}</dd>
        <dt>复习间隔</dt><dd>{p.review_interval_days === null ? unknown : `${p.review_interval_days} 天`}</dd>
        <dt>每天偏好负荷</dt><dd>{p.daily_load_minutes === null ? unknown : `${p.daily_load_minutes} 分钟`}</dd>
        <dt>休闲保护偏好</dt><dd>{p.leisure_protection === null ? unknown : p.leisure_protection === "prefer_protect" ? "优先保护休闲" : "允许灵活取舍"}</dd>
      </dl>
      <p>暂无系统建议。用户设置与系统建议分别记录；本版不生成或自动采纳建议。</p>
      {!editor && !resetConfirm && <div>
        <Button type="button" variant="outline" disabled={locked || profile.isFetching} onClick={() => { setEditor({ revision: profile.data.revision, form: profileForm(profile.data) }); setError(""); setMessage(""); }}>编辑偏好</Button>
        <Button type="button" variant="outline" disabled={locked || profile.isFetching || !profile.data.revision} onClick={() => setResetConfirm(true)}>重置档案</Button>
      </div>}
      {resetConfirm && <div><p>将清空全部偏好并恢复未知，保留课程和任务。</p>
        <Button type="button" variant="outline" disabled={locked} onClick={() => submit(true)}>确认重置偏好</Button>
        <Button type="button" variant="outline" disabled={locked} onClick={() => setResetConfirm(false)}>取消重置</Button>
      </div>}
      {editor && <form onSubmit={e => { e.preventDefault(); void submit(); }}>
        <fieldset disabled={locked}>
          <legend>编辑用户确认的偏好</legend>
          <p>数字留空表示未知；0 表示明确设置为零。这里只记录软偏好，不创建或修改硬约束。</p>
          <div className="grid2">
            <label>IANA 时区<input value={editor.form.timezone} placeholder="例如 Asia/Shanghai" required onChange={e => change({ timezone: e.target.value })} /></label>
            <label>生效日期（可留空）<input type="date" value={editor.form.effective_from} onChange={e => change({ effective_from: e.target.value })} /></label>
            <label>有效截止（可留空）<input type="date" value={editor.form.effective_until} onChange={e => change({ effective_until: e.target.value })} /></label>
            <label>专注时长（5–240 分钟）<input type="number" min="5" max="240" step="1" value={editor.form.focus_minutes} placeholder="未知" onChange={e => change({ focus_minutes: e.target.value })} /></label>
            <label>休息时长（0–120 分钟）<input type="number" min="0" max="120" step="1" value={editor.form.break_minutes} placeholder="未知" onChange={e => change({ break_minutes: e.target.value })} /></label>
            <label>复习间隔（1–365 天）<input type="number" min="1" max="365" step="1" value={editor.form.review_interval_days} placeholder="未知" onChange={e => change({ review_interval_days: e.target.value })} /></label>
            <label>每天偏好负荷（0–720 分钟）<input type="number" min="0" max="720" step="1" value={editor.form.daily_load_minutes} placeholder="未知" onChange={e => change({ daily_load_minutes: e.target.value })} /></label>
            <label>休闲保护偏好<select value={editor.form.leisure_protection ?? ""} onChange={e => change({ leisure_protection: (e.target.value || null) as ProfileForm["leisure_protection"] })}>
              <option value="">未知（未设置）</option><option value="prefer_protect">优先保护休闲</option><option value="flexible">允许灵活取舍</option>
            </select></label>
          </div>
          <WindowEditor title="偏好学习时段" rows={editor.form.preferred_study_windows} onChange={preferred_study_windows => change({ preferred_study_windows })} />
          <WindowEditor title="精力时段" rows={editor.form.energy_windows} energy onChange={energy_windows => change({ energy_windows })} />
          <Button type="submit" variant="outline">确认并保存偏好</Button>
          <Button type="button" variant="outline" onClick={() => { setEditor(null); setError(""); }}>取消编辑</Button>
        </fieldset>
      </form>}
    </>}
    {pending && <p role="status">{busy ? "正在保存…" : "保存结果尚未确认。重试会使用同一请求，避免重复写入。"}</p>}
    {pending && !busy && <Button type="button" variant="outline" onClick={() => submit()}>重试同一次保存</Button>}
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}

export default PersonalProfile;
