import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { api } from "./api";
import { Button } from "./components/ui/button";
import type { Resource } from "./types";

type Item = { content: string; estimated_minutes: number; due_at: string };
type Answer = { course_key: string; status: "pending" | "none" | "homework"; items: Item[] };
type Checkin = { due: boolean; reason: string; date?: string; available_at?: string; timezone?: string;
  courses?: { key: string; name: string; course_id: string }[]; review?: Resource };
type Saved = { review: Resource; task_ids: string[]; complete: boolean; timezone: string;
  blocks: { id: string; title: string; starts_at: string; ends_at: string }[];
  unscheduled: { task_id: string; title: string; remaining_minutes: number; reason: string }[] };
const newItem = (): Item => ({ content: "", estimated_minutes: 45, due_at: "" });
const toInput = (value: string) => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const itemPayload = (item: Item) => ({ ...item, due_at: item.due_at ? new Date(item.due_at).toISOString() : null });
const timeText = (value: string, timezone?: string) => new Date(value).toLocaleString("zh-CN", {
  timeZone: timezone, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
});

/** Opens only on application opening/foreground events. No clock interval. */
export function AfterClassCheckin() {
  const q = useQueryClient();
  const [context, setContext] = useState<Checkin>();
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saved, setSaved] = useState<Saved>();
  const visibleRef = useRef(false), checking = useRef(false);
  const receipt = useRef({ payload: "", key: "" });
  function show(value: boolean) { visibleRef.current = value; setVisible(value); }
  const check = useCallback(async (manual = false) => {
    if (checking.current || visibleRef.current) return;
    checking.current = true;
    try {
      const result = await api<Checkin>("/after-class/open", { method: "POST", body: "{}" });
      if (!result.due || !result.review) {
        if (manual) setNotice(result.reason + (result.available_at ? `；可询问时间：${timeText(result.available_at, result.timezone)}` : ""));
        return;
      }
      setContext(result); setSaved(undefined); setError(""); setNotice("");
      const draft = (result.review.data.draft_answers ?? []) as Answer[];
      setAnswers(result.courses!.map(c => {
        const existing = draft.find(a => a.course_key === c.key);
        return existing ? { ...existing, items: existing.items.map(i => ({ ...i, due_at: i.due_at ? toInput(i.due_at) : "" })) }
          : { course_key: c.key, status: "pending", items: [newItem()] };
      }));
      visibleRef.current = true; setVisible(true);
      // Native bridge may reveal the panel; it receives no homework text.
      window.dispatchEvent(new Event("campus-after-class-ready"));
    } catch (e) {
      if (manual) setNotice(String(e));
    } finally { checking.current = false; }
  }, []);
  useEffect(() => {
    const opened = (e: Event) => { void check(Boolean((e as CustomEvent)?.detail?.manual)); };
    const focused = () => {
      // Native app emits an explicit event when its panel is opened. Browser
      // fallback uses focus only, never elapsed-time polling.
      if (!(window as Window & { __campusPet?: unknown }).__campusPet) void check();
    };
    void check();
    window.addEventListener("campus-after-class-open", opened);
    window.addEventListener("focus", focused);
    return () => { window.removeEventListener("campus-after-class-open", opened); window.removeEventListener("focus", focused); };
  }, [check]);
  const patchAnswer = (index: number, patch: Partial<Answer>) => setAnswers(old => old.map((a, i) => i === index ? { ...a, ...patch } : a));
  const patchItem = (index: number, item: number, patch: Partial<Item>) => setAnswers(old => old.map((a, i) => i === index ? {
    ...a, items: a.items.map((value, j) => j === item ? { ...value, ...patch } : value),
  } : a));
  async function defer() {
    if (busy) return;
    if (!context?.review || saved) { show(false); return; }
    setBusy(true); setError("");
    try {
      const review = await api<Resource>(`/after-class/${context.review.id}/draft`, {
        method: "PUT", body: JSON.stringify({ revision: context.review.revision,
          answers: answers.map(a => ({ ...a, items: a.items.map(itemPayload) })) }),
      });
      setContext({ ...context, review }); show(false);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  return <>
    {notice && <section className="card after-class-notice" role="status"><p>{notice}</p><Button variant="outline" onClick={() => setNotice("")}>知道了</Button></section>}
    <Dialog.Root open={visible} onOpenChange={value => { if (!value) void defer(); }}>
      <Dialog.Portal><Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="import-dialog after-class-dialog" onInteractOutside={e => e.preventDefault()}>
          <header><div><p className="eyebrow">课间奶娃 · 课后小结</p>
            <Dialog.Title asChild><h2>{saved ? "作业已记下" : "今天这些课，布置了什么作业？"}</h2></Dialog.Title></div>
            <Button type="button" variant="outline" disabled={busy} onClick={() => void defer()}>{saved ? "完成" : "稍后填写"}</Button>
          </header>
          <Dialog.Description>{saved ? "已填写的科目不会重复询问。作业和学习安排都可以继续修改。"
            : `${context?.date ?? ""} · 全部课程结束后再一起回顾。稍后填写会保留已填内容，下次打开时继续。`}</Dialog.Description>
          {error && <p role="alert">{error}</p>}
          {saved ? <div className="after-class-result" data-after-class-result>
            <p role="status">已保存 {saved.task_ids.length} 项作业，加入 {saved.blocks.length} 个学习时间块。{saved.complete ? "当天科目已全部填写。" : "其他科目可以下次继续填写。"}</p>
            {saved.blocks.map(b => <div className="step" key={b.id}><strong>{b.title}</strong><p>{timeText(b.starts_at, saved.timezone)} – {timeText(b.ends_at, saved.timezone)}</p></div>)}
            {saved.unscheduled.length > 0 && <section role="alert"><h3>这些内容还没排完</h3>{saved.unscheduled.map(u => <p key={u.task_id}>{u.title}：剩余 {u.remaining_minutes} 分钟。{u.reason}</p>)}<p>作业已保存在待办中，可修改耗时、截止时间或学习窗口后重新规划。</p></section>}
            <div className="guide-actions"><Button onClick={() => { show(false); window.dispatchEvent(new CustomEvent("campus-calendar-saved", {
              detail: saved.blocks[0] ? new Date(saved.blocks[0].starts_at).toLocaleDateString("en-CA", { timeZone: saved.timezone }) : context?.date,
            })); }}>查看日程</Button>
              {!saved.complete && <Button variant="outline" onClick={() => { show(false); void check(true); }}>继续填写其他科目</Button>}</div>
          </div> : <form data-after-class-form onSubmit={async e => {
            e.preventDefault(); if (!context?.review || busy) return;
            const selected = answers.filter(a => a.status !== "pending");
            if (!selected.length) { setError("请至少填写一门课，或选择这门课没有作业。"); return; }
            setBusy(true); setError("");
            try {
              const payload = JSON.stringify({ revision: context.review.revision,
                answers: selected.map(a => ({ ...a, items: a.status === "none" ? [] : a.items.map(itemPayload) })) });
              const identity = context.review.id + payload;
              if (receipt.current.payload !== identity) receipt.current = { payload: identity, key: crypto.randomUUID() };
              const result = await api<Saved>(`/after-class/${context.review.id}/submit`, {
                method: "POST", headers: { "Idempotency-Key": receipt.current.key }, body: payload,
              });
              setSaved(result); setContext({ ...context, review: result.review });
              void q.invalidateQueries();
            } catch (err) { setError(String(err)); }
            finally { setBusy(false); }
          }}>
            {(context?.courses ?? []).map((course, index) => <section className="card after-class-course" key={course.key}>
              <h3>{course.name}</h3><label>这门课的作业情况<select aria-label={`${course.name}的作业情况`} value={answers[index]?.status ?? "pending"} disabled={busy}
                onChange={e => patchAnswer(index, { status: e.target.value as Answer["status"] })}>
                <option value="pending">还没填写</option><option value="homework">有作业</option><option value="none">没有作业</option>
              </select></label>
              {answers[index]?.status === "homework" && <>
                {answers[index].items.map((item, j) => <fieldset key={j} disabled={busy} className="after-class-item"><legend>作业 {j + 1}</legend>
                  <label>作业内容<textarea required maxLength={4000} rows={3} value={item.content} onChange={e => patchItem(index, j, { content: e.target.value })} placeholder="例如：完成第三章习题 1～5" /></label>
                  <div className="grid2"><label>预计用时（分钟）<input required type="number" min={5} max={240} value={item.estimated_minutes} onChange={e => patchItem(index, j, { estimated_minutes: Number(e.target.value) })} /></label>
                    <label>截止时间（{Intl.DateTimeFormat().resolvedOptions().timeZone}）<input type="datetime-local" value={item.due_at} onChange={e => patchItem(index, j, { due_at: e.target.value })} /></label></div>
                  {answers[index].items.length > 1 && <Button type="button" variant="outline" onClick={() => patchAnswer(index, { items: answers[index].items.filter((_, k) => k !== j) })}>移除这项</Button>}
                </fieldset>)}
                <Button type="button" variant="outline" disabled={busy || answers[index].items.length >= 12} onClick={() => patchAnswer(index, { items: [...answers[index].items, newItem()] })}>再加一项作业</Button>
              </>}
            </section>)}
            <p>截止时间可留空，会标记为待补充；仍可安排学习时间。按所填用时，在未来 7 天避开课程和已有日程。未填写的科目下次继续。</p>
            <Button disabled={busy}>{busy ? "正在保存和安排…" : "保存作业并加入日程"}</Button>
          </form>}
        </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  </>;
}

export function AfterClassPreferences() {
  const q = useQueryClient();
  const pref = useQuery({ queryKey: ["after-class-preferences"], queryFn: () => api<Resource>("/after-class/preferences") });
  const [enabled, setEnabled] = useState(true), [delay, setDelay] = useState(30);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  useEffect(() => { if (pref.data) { setEnabled(pref.data.data.enabled); setDelay(pref.data.data.delay_minutes); } }, [pref.data]);
  return <section className="card"><h2>课后作业询问</h2>
    <p>当天全部课程结束后，达到等待时间，再次打开或唤出奶娃 App 时询问。不会按时自动弹窗。</p>
    {pref.error && <p role="alert">{String(pref.error)}</p>}
    <form onSubmit={async e => {
      e.preventDefault(); if (!pref.data) return;
      setBusy(true); setMessage("");
      try { await api("/after-class/preferences", { method: "PUT", body: JSON.stringify({ revision: pref.data.revision, enabled, delay_minutes: delay }) });
        await q.invalidateQueries({ queryKey: ["after-class-preferences"] }); setMessage("课后询问设置已保存");
      } catch (err) { setMessage(String(err)); } finally { setBusy(false); }
    }}><label className="check"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />开启课后作业询问</label>
      <label>最后一节课结束后等待（分钟）<input type="number" required min={0} max={180} value={delay} onChange={e => setDelay(Number(e.target.value))} /></label>
      <Button disabled={busy || !pref.data}>保存询问设置</Button>{message && <p role="status">{message}</p>}
    </form>
  </section>;
}
