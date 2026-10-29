import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { PlanReview } from "./Today";
import type { Resource } from "./types";
import { Button } from "./components/ui/button";
import { currentReviewWeek, mondayOf, reviewActionOperation, reviewPlanOperation, linkedPlanLabel, secondsLabel, type ReviewPlanOperation, type PlanTotal, type ReviewAction, type ReviewOperation, type ReviewState, type WeeklyReviewView } from "./weekly-review-state";

const feedback: Record<string, string> = { partial: "部分完成", completed: "本次执行已完成", not_started: "未开始", skipped: "已跳过" };
const reasons: Record<string, string> = { interrupted: "受到中断", insufficient_time: "时间不足", unsuitable_schedule: "安排不合适", skipped: "选择跳过", other: "其他原因" };
const gapLabels: Record<string, string> = { ambiguous_completion_week: "跨周执行的完成日期仍需核对，尚未计入本周任务完成数", incomplete_original_baseline: "原始周基线不完整", original_recorded_after_week_start: "原始计划在本周开始后才有记录", snapshot_timezone_mismatch: "历史计划使用不同的时区，覆盖日期待核对", invalid_snapshot_scope: "历史计划的日期范围待核对", conflicting_snapshot_block: "历史安排有冲突版本", invalid_snapshot_block: "部分历史安排缺少可靠时间", invalid_current_block: "部分当前安排缺少可靠时间", missing_execution: "部分安排还没有执行反馈", ambiguous_execution_week: "部分记录无法准确归入本周", unconfirmed_execution_interval: "计时有待确认的离线间隔", undated_task_completion: "部分已完成任务没有完成日期依据" };
const statusLabels: Record<string, string> = { awaiting_choice: "尚未选择", accepted_pending_integration: "已接受调整意向，可生成下周计划草稿", rejected: "暂不采纳" };

function Planned({ title, value }: { title: string; value: PlanTotal }) {
  return <article className="card"><h4>{title}</h4>
    <p>{value.status === "missing" ? "未知（没有覆盖本周的计划快照）" : value.status === "partial" ? `已知部分 ${value.known_minutes} 分钟 · 周基线不完整` : `${value.minutes} 分钟`}</p>
    {!!value.covered_dates.length && <p>有记录的日期：{value.covered_dates.join("、")}</p>}
    <details><summary>核对计划来源</summary>
      {!!value.snapshot_ids.length && <p>计划快照：{value.snapshot_ids.join("、")}</p>}
      {value.blocks.map(b => <p key={b.plan_block_id}>{b.title} · {secondsLabel(b.seconds)} · 安排 {b.plan_block_id}</p>)}
      {!value.blocks.length && <p>没有可核对的安排记录。</p>}
    </details>
  </article>;
}

export function WeeklyReview() {
  const q = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<{ data: { timezone: string } }>("/settings") });
  const [selectedWeek, setWeek] = useState("");
  const [selectedZone, setZone] = useState("");
  const [zoneDraft, setZoneDraft] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<ReviewOperation | null>(null);
  const [pendingPlan, setPendingPlan] = useState<ReviewPlanOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const timezone = selectedZone || settings.data?.data.timezone || "Asia/Shanghai";
  const week = selectedWeek || currentReviewWeek(timezone);
  const review = useQuery({ queryKey: ["weekly-review", week, timezone], queryFn: () => api<WeeklyReviewView>(`/weekly-review?week_start=${week}&timezone=${encodeURIComponent(timezone)}`), enabled: !!settings.data });
  const report = review.data;
  const locked = busy || !!pending || !!pendingPlan;

  async function save(action: ReviewAction = "reason") {
    if (busyRef.current || !report) return;
    setError(""); setMessage("");
    let operation = pending;
    if (!operation) {
      try { operation = reviewActionOperation(report.week_start, report.timezone, report.review.revision, report.source_revision, action, reason); }
      catch (e) { setError(String(e)); return; }
      setPending(operation);
    }
    busyRef.current = true; setBusy(true);
    try {
      await api<ReviewState>("/weekly-review/actions", { method: "POST", headers: { "Idempotency-Key": operation.idempotencyKey }, body: JSON.stringify(operation.body) });
      setPending(null);
      setMessage(operation.body.action === "accept" ? "调整意向已保存，可以生成下周计划草稿并校对确认。" : "复盘选择已保存。");
      await q.invalidateQueries();
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        setPending(null);
        if (e.status === 409) await q.invalidateQueries({ queryKey: ["weekly-review"] });
      }
      setError(String(e));
    } finally { busyRef.current = false; setBusy(false); }
  }

  async function createPlan() {
    if (busyRef.current || !report) return;
    setError(""); setMessage("");
    let operation = pendingPlan;
    if (!operation) {
      try { operation = reviewPlanOperation(report); }
      catch(e) {setError(String(e));return;}
      setPendingPlan(operation);
    }
    busyRef.current = true; setBusy(true);
    try {
      const result = await api<{draft:Resource}>(operation.path, {method:"POST",headers:{"Idempotency-Key":operation.idempotencyKey},body:JSON.stringify(operation.body)});
      setPendingPlan(null);
      setMessage(`${operation.targetWeek} 起的下周草稿已生成，请在下方核对并确认。`);
      await q.invalidateQueries();
      // The read projection carries the original Resource into PlanReview;
      // the draft response is retained by the server receipt for lost retries.
      if (!result.draft) throw new Error("计划草稿未返回，请刷新核对状态");
    } catch(e) {
      if(e instanceof ApiError && e.status >= 400 && e.status < 500) {
        setPendingPlan(null);
        if(e.status === 409) await q.invalidateQueries();
      }
      setError(String(e));
    } finally {busyRef.current=false;setBusy(false);}
  }

  function changeWeek(value: string) {
    try { setWeek(mondayOf(value)); setReason(""); setError(""); setMessage(""); }
    catch (e) { setError(String(e)); }
  }

  return <section aria-label="每周复盘">
    <h3>每周复盘</h3>
    <p>核对计划和实际投入，记录遇到的情况与下周想调整的内容。周一开始，截止到下周一零点。</p>
    <div className="grid2">
      <label>选择周内日期<input type="date" value={week} disabled={locked} onChange={e => e.target.value && changeWeek(e.target.value)} /></label>
      <label>复盘时区<input value={zoneDraft} disabled={locked} placeholder={timezone} onChange={e => setZoneDraft(e.target.value)} /></label>
    </div>
    <Button type="button" variant="outline" disabled={locked || !settings.data} onClick={() => {
      try { const zone = zoneDraft.trim() || settings.data!.data.timezone; new Intl.DateTimeFormat("zh-CN", { timeZone: zone }).format(); setZone(zone); setError(""); setMessage(""); }
      catch { setError("请输入有效时区，例如 Asia/Shanghai。"); }
    }}>使用此时区</Button>
    <p>当前按 {timezone} 核对。历史记录保留各自记录时的日期和时区。</p>
    {(settings.isPending || (settings.data && review.isPending)) && <p role="status">正在读取周复盘…</p>}
    {(settings.error || review.error) && <><p role="alert">周复盘读取失败：{String(settings.error || review.error)}</p><Button type="button" variant="outline" disabled={locked} onClick={() => { void settings.refetch(); void review.refetch(); }}>重试读取</Button></>}
    {report && <>
      <p>{report.week_start} 至 {report.week_end}（不含截止日）</p>
      <div className="grid2"><Planned title="原始计划" value={report.plans.original} /><Planned title="调整后计划" value={report.plans.adjusted} /><Planned title="当前安排" value={report.plans.current} /></div>
      <article className="card"><h4>实际投入</h4>
        <p>本周实际总量：{secondsLabel(report.execution.actual_seconds)}</p>
        <p>已记录投入小计：{secondsLabel(report.execution.observed_seconds)}</p>
        <p>未记录的投入保持未知；已记录的小计可能尚不完整。</p>
        <p>本周有日期依据的任务完成：{report.execution.completed_task_ids.length} 项</p>
        {!!report.execution.completed_task_ids.length && <p>{report.execution.completed_task_ids.map(id => report.execution.records.find(r => r.task_id === id)?.task_title || id).join("、")}</p>}
        {!!report.execution.undated_completed_task_ids.length && <p>另有 {report.execution.undated_completed_task_ids.length} 项已完成任务缺少完成日期，未计入本周完成数。</p>}
        {!!report.execution.missing_plan_block_ids.length && <p>缺少执行反馈的安排：{report.execution.missing_plan_block_ids.length} 项</p>}
      </article>
      {!!report.gaps.length && <div role="note"><h4>本周待核对</h4><ul>{report.gaps.map(g => <li key={g}>{gapLabels[g] || "有一项资料需要核对"}</li>)}</ul></div>}
      <h4>执行记录</h4>
      {!report.execution.records.length && <p>本周暂无可归属的执行记录，实际投入未知。</p>}
      {report.execution.records.map(r => <article className="card" key={r.record_id}>
        <h5>{r.task_title}</h5><p>{r.performed_on} · {r.timezone} · {r.source === "timer" ? "计时记录" : "手工记录"}</p>
        <p>{feedback[r.feedback] || "反馈待核对"} · {secondsLabel(r.observed_seconds)}</p>
        {r.actual_seconds === null && <p>实际总量尚未确认。</p>}
        {r.allocation_status === "ambiguous" && <p>日期或时区边界待核对，尚未加入已记录投入小计。</p>}
        {r.unfinished_reason ? <p>用户记录的原因：{reasons[r.unfinished_reason] || r.unfinished_reason}</p> : r.reason_prompt && <p>{r.reason_prompt}</p>}
        <details><summary>核对执行来源</summary><p>执行记录：{r.record_id}</p>{r.plan_block_ids.length > 0 && <p>关联安排：{r.plan_block_ids.join("、")}</p>}{r.supersedes_id && <p>更正原记录：{r.supersedes_id}（已使用更正后的数值）</p>}{r.timer_id && <p>计时记录：{r.timer_id}</p>}</details>
      </article>)}
      <article className="card"><h4>历史估算</h4><p>可归到本周的历史估算：{report.estimates.allocated_minutes} 分钟。估算单独列出，不计入实际投入。</p>
        {!!report.estimates.unallocated.length && <p>另有 {report.estimates.unallocated.length} 项估算无法确定所属周，未加入本周估算合计。</p>}
        <details><summary>核对估算来源</summary>{report.estimates.allocations.map((e, i) => <p key={i}>安排 {e.plan_block_id} · {e.minutes} 分钟{e.baseline_id && ` · 历史记录 ${e.baseline_id}`}</p>)}{report.estimates.unallocated.map((e, i) => <p key={`u${i}`}>步骤 {e.step_id} · {e.minutes} 分钟 · 所属周未知{e.baseline_id && ` · 历史记录 ${e.baseline_id}`}</p>)}</details>
      </article>
      <h4>原因与下周调整</h4>
      <p>接受意向后，可明确生成复盘周下一周的计划草稿。草稿按已确认的任务、课程与排程设置计算；文字意向保留为来源，时间偏好或禁排仍需先通过相应入口确认。</p>
      <p>当前选择：{statusLabels[report.review.data.status] || "待核对"}</p>
      {report.review.data.reason && <p>已保存内容：{report.review.data.reason}</p>}
      <label>这周遇到的情况，或下周想怎样调整<textarea value={reason} maxLength={2000} disabled={locked} onChange={e => setReason(e.target.value)} /></label>
      <div>
        <Button type="button" variant="outline" disabled={locked || review.isFetching} onClick={() => save("reason")}>保存原因</Button>
        <Button type="button" variant="outline" disabled={locked || review.isFetching} onClick={() => save("accept")}>接受这项调整意向</Button>
        <Button type="button" variant="outline" disabled={locked || review.isFetching} onClick={() => save("reject")}>暂不采纳</Button>
        <Button type="button" variant="outline" disabled={locked || review.isFetching || report.review.data.status === "awaiting_choice"} onClick={() => save("restore")}>恢复为待选择</Button>
      </div>
      <article className="card" aria-label="复盘关联的下周计划">
        <h4>下周计划 · {report.next_week_plan?.week_start || '待读取'}</h4>
        <p>{linkedPlanLabel(report.next_week_plan?.status || 'not_created')}</p>
        {report.next_week_plan?.status === 'invalidated' && <p>原草稿不能继续确认。请核对最新资料，再明确生成新的草稿。</p>}
        {report.next_week_plan?.status === 'confirmed' && <p>已确认快照：{report.next_week_plan.snapshot_ids.join('、')}。可在日历切换到 {report.next_week_plan.week_start} 核对正式安排。恢复复盘意向会保留这些安排和快照。</p>}
        <Button type="button" variant="outline" disabled={locked || review.isFetching || report.review.data.status !== 'accepted_pending_integration' || report.next_week_plan?.status === 'pending' || (report.next_week_plan?.status === 'confirmed' && report.next_week_plan.is_current_intent !== false)} onClick={()=>void createPlan()}>生成下周计划草稿</Button>
        {report.next_week_plan?.status === 'pending' && report.next_week_plan.draft && <PlanReview draft={report.next_week_plan.draft} key={report.next_week_plan.draft.id}/>}
      </article>
      {!!report.review.data.history.length && <details><summary>查看复盘选择历史</summary>{report.review.data.history.map((h, i) => <p key={i}>{h.recorded_at} · {{ accept: "接受调整意向", reject: "暂不采纳", restore: "恢复待选择", reason: "补充原因" }[h.action]}{h.reason && ` · ${h.reason}`}</p>)}</details>}
    </>}
    {pending && <p role="status">{busy ? "正在保存…" : "保存结果尚未确认，重试会核对同一次操作。"}</p>}
    {pending && !busy && <Button type="button" variant="outline" onClick={() => save()}>重试同一次保存</Button>}
    {pendingPlan && <p role="status">{busy ? "正在生成下周计划草稿…" : "生成结果尚未确认，重试会核对同一次请求。"}</p>}
    {pendingPlan && !busy && <Button type="button" variant="outline" onClick={()=>void createPlan()}>重试同一次草稿生成</Button>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
export default WeeklyReview;
