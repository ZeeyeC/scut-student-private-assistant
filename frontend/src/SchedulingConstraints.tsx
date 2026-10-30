import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Resource } from "./types";
import { Button } from "./components/ui/button";
import { DraftActions } from "./Assignments";
import { constraintInput, constraintInstant } from "./constraint-time";
import { DateTime } from "luxon";

const format = (value: string, timezone: string) =>
  new Date(value).toLocaleString("zh-CN", { timeZone: timezone, hour12: false });
const weekNames = ["一", "二", "三", "四", "五", "六", "日"];
const weekday = (value:string) => new Date(value.slice(0,10)+"T00:00:00Z").getUTCDay() || 7;
function previewLastDay(value:string) {
  const day=new Date(value+"T00:00:00Z");
  if(!value || !Number.isFinite(day.getTime()))return null;
  day.setUTCDate(day.getUTCDate()+13);
  return day.toISOString().slice(0,10);
}
function ConstraintSummary({data:c}:{data:Resource["data"]}) {
  if(c.recurrence!=="weekly")return <p>{format(c.starts_at,c.timezone)} 至 {format(c.ends_at,c.timezone)}（{c.timezone}）</p>;
  const a=DateTime.fromISO(c.starts_at).setZone(c.timezone), b=DateTime.fromISO(c.ends_at).setZone(c.timezone);
  return <p>每周{c.weekdays.map((d:number)=>weekNames[d-1]).join("、")} · {a.toFormat("HH:mm")} 至 {a.toFormat("yyyy-MM-dd")!==b.toFormat("yyyy-MM-dd")?"次日 ":""}{b.toFormat("HH:mm")}（{c.timezone}）；{a.toFormat("yyyy-MM-dd")} 起，{c.valid_until?`至 ${c.valid_until}（含当天）`:"长期有效"}</p>;
}

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
    <p>为休息或私人事项留出时间，可只写“不可安排”。支持单次或每周重复，也可选择软偏好优先学习时段；硬禁排会避让，软偏好可让步。已有日程会保留，重新规划并确认后才调整；锁定安排如有冲突会提示。</p>
    {(settings.error || constraints.error || drafts.error) && <p role="alert">{String(settings.error || constraints.error || drafts.error)}</p>}
    {constraints.isPending && <p role="status">正在读取禁排时段…</p>}
    {constraints.data?.length === 0 && <p>还没有已保存的禁排时段。</p>}
    {constraints.data?.map(r => <article key={r.id} className="step">
      <h3>{r.data.title} · {r.data.active ? "已启用" : "已停用"}</h3>
      <p>{r.data.strength==="soft"?"软偏好（优先学习，可让步）":"硬禁排（不安排任务）"}</p>
      <ConstraintSummary data={r.data} />
      <Button variant="outline" disabled={busy || constraints.isFetching} onClick={() => setEditor(r)}>修改时段</Button>
      <Button variant="outline" disabled={busy || constraints.isFetching} onClick={async () => {
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
  const [strength, setStrength] = useState(original?.strength ?? "hard");
  const [title, setTitle] = useState(original?.title ?? "不可安排");
  const [start, setStart] = useState(original ? constraintInput(original.starts_at, timezone) : "");
  const [end, setEnd] = useState(original ? constraintInput(original.ends_at, timezone) : "");
  const [recurrence,setRecurrence]=useState(original?.recurrence??"once");
  const [weekdays,setWeekdays]=useState<number[]>(original?.weekdays??[]);
  const [until,setUntil]=useState(original?.valid_until??"");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const request = useRef({ body: "", key: "" });
  return <form aria-label="编辑禁排时段" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const starts_at = constraintInstant(start, timezone), ends_at = constraintInstant(end, timezone);
      if (Date.parse(ends_at) <= Date.parse(starts_at)) throw new Error("结束时间必须晚于开始时间。");
      const payload = {
        constraint: { title, strength, recurrence, timezone, starts_at, ends_at,
          weekdays:recurrence==="weekly"?weekdays:[],valid_until:recurrence==="weekly"?(until||null):null },
        constraint_id: draft?.data.payload.constraint_id ?? target?.id ?? null,
        constraint_revision: draft?.data.payload.constraint_revision ?? target?.revision ?? null,
      };
      const body = JSON.stringify(draft ? { revision: draft.revision, payload } : payload);
      if (request.current.body !== body) request.current = { body, key: crypto.randomUUID() };
      await api(draft ? `/drafts/${draft.id}` : "/drafts/scheduling-constraint", { method: draft ? "PUT" : "POST", body, headers: { "Idempotency-Key": request.current.key } });
      await q.invalidateQueries({ queryKey: ["drafts"] }); onDone();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }}>
    <h3>{draft || target ? "修改禁排草稿" : "新增禁排"}</h3>
    <p>以下时间均按 {timezone} 解释，与电脑当前时区无关。</p>
    <label>禁排名称<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
    <label>约束类型<select value={strength} onChange={e=>setStrength(e.target.value)}><option value="hard">硬禁排（不安排任务）</option><option value="soft">软偏好（优先学习，可让步）</option></select></label>
    <label>重复方式<select value={recurrence} onChange={e=>{setRecurrence(e.target.value);if(e.target.value==="weekly"&&!weekdays.length&&start)setWeekdays([weekday(start)]);}}><option value="once">仅这一次</option><option value="weekly">每周重复</option></select></label>
    <div className="grid2">
      <label>禁排开始<input type="datetime-local" required value={start} onChange={e => {setStart(e.target.value);if(recurrence==="weekly"&&!weekdays.length&&e.target.value)setWeekdays([weekday(e.target.value)]);}} /></label>
      <label>禁排结束<input type="datetime-local" required value={end} onChange={e => setEnd(e.target.value)} /></label>
    </div>
    {recurrence==="weekly" && <fieldset><legend>每周哪些天</legend>
      {weekNames.map((n,i)=><label className="check" key={n}><input type="checkbox" checked={weekdays.includes(i+1)} onChange={e=>setWeekdays(e.target.checked?[...weekdays,i+1].sort((a,b)=>a-b):weekdays.filter(d=>d!==i+1))} />每周{n}</label>)}
      <label>重复截止日期（可留空）<input type="date" min={start.slice(0,10)} value={until} onChange={e=>setUntil(e.target.value)} /></label>
      <p>开始日期为生效起日，按所选星期重复同样的钟点；跨午夜请把结束填到次日。截止日期含当天，留空长期有效。</p>
    </fieldset>}
    {error && <p role="alert">{error}</p>}
    <Button disabled={busy}>{busy ? "正在保存草稿…" : draft ? "保存校对修改" : "生成禁排草稿"}</Button>
    <Button type="button" variant="outline" disabled={busy} onClick={onDone}>取消编辑</Button>
  </form>;
}

export function ConstraintReview({ draft }: { draft: Resource }) {
  const p = draft.data.payload, c = p.constraint;
  const [editing, setEditing] = useState(false), [error, setError] = useState("");
  const [previewStart,setPreviewStart]=useState(constraintInput(c.starts_at,c.timezone).slice(0,10));
  const previewEnd=previewLastDay(previewStart);
  const preview=useQuery({queryKey:["constraint-preview",draft.id,draft.revision,previewStart],enabled:!!previewEnd,queryFn:()=>api<{windows:Resource[];affected_plans:Resource[];active_after_save:boolean}>(`/drafts/${draft.id}/constraint-preview?start=${previewStart}&end=${previewEnd}`,{method:"POST",body:JSON.stringify({revision:draft.revision,payload:p})})});
  const impacted=preview.data?.affected_plans??[];
  return <section aria-label="禁排草稿" className="step">
    <p className="eyebrow">禁排草稿 · 尚未生效</p>
    <h3>{p.constraint_id ? "校对禁排修改" : "校对新增禁排"}：{c.title}</h3>
    <ConstraintSummary data={c} />
    <p>{c.strength==="soft"?"软偏好：仅在选择遵循偏好的方案时优先使用，不占用或禁止其他时间。":"硬约束"} · {c.recurrence==="weekly"?"每周重复":"仅这一次"}。确认后仅影响后续规划；不会自动移动课程或已保存的任务。修改已停用的时段后仍保持停用。</p>
    <label>预览起日<input type="date" value={previewStart} onChange={e=>setPreviewStart(e.target.value)} /></label>
    <p>预览 {previewStart} 至 {previewEnd??"请选择日期"} 的发生时间：</p>
    {preview.isFetching && <p role="status">正在预览禁排…</p>}
    {preview.error && <p role="alert">无法预览：{String(preview.error)}</p>}
    {preview.data && <div aria-label="禁排发生预览">{preview.data.windows.length===0?<p>这个日期范围内没有禁排。</p>:preview.data.windows.map(w=><p key={w.id}>{format(w.data.starts_at,c.timezone)} 至 {format(w.data.ends_at,c.timezone)}</p>)}</div>}
    {impacted.length > 0 && <div role="status"><p>与以下已有安排重叠，请在保存禁排后重新规划：</p>{impacted.map(b => <p key={b.id}>{b.data.title ?? "学习安排"}{b.data.locked ? "（已锁定，需要你处理冲突）" : "（确认新计划前保持原样）"}</p>)}</div>}
    <Button variant="outline" onClick={() => setEditing(v => !v)}>{editing ? "收起编辑" : "修改草稿"}</Button>
    {editing ? <ConstraintEditor timezone={c.timezone} draft={draft} onDone={() => setEditing(false)} /> : <DraftActions draft={draft} payload={p} onError={setError} canSave={!!preview.data&&!preview.error&&!preview.isFetching} blockedMessage="请先读取禁排预览，或修改无效的规则。" />}
    {error && <p role="alert">{error}</p>}
  </section>;
}
