import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Resource } from "./types";
import { Button } from "./components/ui/button";
import { DraftActions } from "./Assignments";
import { constraintInput, constraintInstant } from "./constraint-time";

const format = (value: string, timezone: string) =>
  new Date(value).toLocaleString("zh-CN", { timeZone: timezone, hour12: false });

export function SchedulingConstraints() {
  const q = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<Resource>("/settings") });
  const constraints = useQuery({ queryKey: ["scheduling-constraints"], queryFn: () => api<Resource[]>("/scheduling-constraints") });
  const drafts = useQuery({ queryKey: ["drafts"], queryFn: () => api<Resource[]>("/drafts") });
  const [editor, setEditor] = useState<Resource | "new" | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const timezone = settings.data?.data.timezone;
  return <section className="card" aria-label="禁排时段">
    <h2>禁排时段</h2>
    <p>为休息或私人事项留出时间，可只写“不可安排”。首版支持单次时段；确认后，新计划会避开它。已有日程会保留，重新规划并确认后才调整；锁定安排如有冲突会提示。</p>
    {(settings.error || constraints.error || drafts.error) && <p role="alert">{String(settings.error || constraints.error || drafts.error)}</p>}
    {constraints.isPending && <p role="status">正在读取禁排时段…</p>}
    {constraints.data?.length === 0 && <p>还没有已保存的禁排时段。</p>}
    {constraints.data?.map(r => <article key={r.id} className="step">
      <h3>{r.data.title} · {r.data.active ? "已启用" : "已停用"}</h3>
      <p>{format(r.data.starts_at, r.data.timezone)} 至 {format(r.data.ends_at, r.data.timezone)}（{r.data.timezone}）</p>
      <Button variant="outline" disabled={busy} onClick={() => setEditor(r)}>修改时段</Button>
      <Button variant="outline" disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try {
          await api(`/scheduling-constraints/${r.id}`, { method: "PATCH", body: JSON.stringify({ revision: r.revision, active: !r.data.active }), headers: { "Idempotency-Key": `${r.id}:${r.revision}:${!r.data.active}` } });
          await q.invalidateQueries();
        } catch (e) { setError(String(e)); } finally { setBusy(false); }
      }}>{r.data.active ? "停用禁排" : "启用禁排"}</Button>
    </article>)}
    <Button variant="outline" disabled={!timezone || busy} onClick={() => setEditor("new")}>添加禁排时段</Button>
    {editor && timezone && <ConstraintEditor key={editor === "new" ? "new" : `${editor.id}:${editor.revision}`} timezone={editor === "new" ? timezone : editor.data.timezone} target={editor === "new" ? undefined : editor} onDone={() => setEditor(null)} />}
    {drafts.data?.filter(d => d.data.draft_kind === "scheduling_constraint").map(d => <ConstraintReview key={`${d.id}:${d.revision}`} draft={d} />)}
    {error && <p role="alert">{error}</p>}
    <Button variant="outline" onClick={() => { void q.invalidateQueries(); }}>刷新禁排与草稿</Button>
  </section>;
}

function ConstraintEditor({ timezone, target, draft, onDone }: { timezone: string; target?: Resource; draft?: Resource; onDone: () => void }) {
  const q = useQueryClient();
  const original = draft?.data.payload.constraint ?? target?.data;
  const [title, setTitle] = useState(original?.title ?? "不可安排");
  const [start, setStart] = useState(original ? constraintInput(original.starts_at, timezone) : "");
  const [end, setEnd] = useState(original ? constraintInput(original.ends_at, timezone) : "");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const request = useRef({ body: "", key: "" });
  return <form aria-label="编辑禁排时段" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const starts_at = constraintInstant(start, timezone), ends_at = constraintInstant(end, timezone);
      if (Date.parse(ends_at) <= Date.parse(starts_at)) throw new Error("结束时间必须晚于开始时间。");
      const payload = {
        constraint: { title, strength: "hard", recurrence: "once", timezone, starts_at, ends_at },
        constraint_id: draft?.data.payload.constraint_id ?? target?.id ?? null,
        constraint_revision: draft?.data.payload.constraint_revision ?? target?.revision ?? null,
      };
      const body = JSON.stringify(draft ? { revision: draft.revision, payload } : payload);
      if (request.current.body !== body) request.current = { body, key: crypto.randomUUID() };
      await api(draft ? `/drafts/${draft.id}` : "/drafts/scheduling-constraint", { method: draft ? "PUT" : "POST", body, headers: { "Idempotency-Key": request.current.key } });
      await q.invalidateQueries({ queryKey: ["drafts"] }); onDone();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }}>
    <h3>{draft || target ? "修改禁排草稿" : "新增单次禁排"}</h3>
    <p>以下时间均按 {timezone} 解释，与电脑当前时区无关。</p>
    <label>禁排名称<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
    <div className="grid2">
      <label>禁排开始<input type="datetime-local" required value={start} onChange={e => setStart(e.target.value)} /></label>
      <label>禁排结束<input type="datetime-local" required value={end} onChange={e => setEnd(e.target.value)} /></label>
    </div>
    {error && <p role="alert">{error}</p>}
    <Button disabled={busy}>{busy ? "正在保存草稿…" : draft ? "保存校对修改" : "生成禁排草稿"}</Button>
    <Button type="button" variant="outline" disabled={busy} onClick={onDone}>取消编辑</Button>
  </form>;
}

export function ConstraintReview({ draft }: { draft: Resource }) {
  const p = draft.data.payload, c = p.constraint;
  const [editing, setEditing] = useState(false), [error, setError] = useState("");
  const blocks = useQuery({ queryKey: ["plan-blocks"], queryFn: () => api<Resource[]>("/plan-blocks") });
  const impacted = blocks.data?.filter(b => b.data.status !== "completed" && Date.parse(b.data.ends_at) > Date.now() && Date.parse(b.data.starts_at) < Date.parse(c.ends_at) && Date.parse(b.data.ends_at) > Date.parse(c.starts_at)) ?? [];
  return <section aria-label="禁排草稿" className="step">
    <p className="eyebrow">禁排草稿 · 尚未生效</p>
    <h3>{p.constraint_id ? "校对禁排修改" : "校对新增禁排"}：{c.title}</h3>
    <p>{format(c.starts_at, c.timezone)} 至 {format(c.ends_at, c.timezone)}（{c.timezone}）</p>
    <p>硬约束 · 仅这一次。确认后仅影响后续规划；不会自动移动课程或已保存的任务。修改已停用的时段后仍保持停用。</p>
    {blocks.error && <p role="alert">无法读取已有安排：{String(blocks.error)}</p>}
    {impacted.length > 0 && <div role="status"><p>与以下已有安排重叠，请在保存禁排后重新规划：</p>{impacted.map(b => <p key={b.id}>{b.data.title ?? "学习安排"}{b.data.locked ? "（已锁定，需要你处理冲突）" : "（确认新计划前保持原样）"}</p>)}</div>}
    <Button variant="outline" onClick={() => setEditing(v => !v)}>{editing ? "收起编辑" : "修改草稿"}</Button>
    {editing ? <ConstraintEditor timezone={c.timezone} draft={draft} onDone={() => setEditing(false)} /> : <DraftActions draft={draft} payload={p} onError={setError} />}
    {error && <p role="alert">{error}</p>}
  </section>;
}
