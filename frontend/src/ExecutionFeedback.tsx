import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Resource } from "./types";
import { Button } from "./components/ui/button";
import { executionDisplay, newExecutionOperation, type ExecutionSummary } from "./execution-state";

type Operation = ReturnType<typeof newExecutionOperation<Record<string, unknown>>>;

export function ExecutionFeedback({ task, step, block }: { task: Resource; step?: Resource; block?: Resource }) {
  const q = useQueryClient();
  const [minutes, setMinutes] = useState("");
  const [feedback, setFeedback] = useState("partial");
  const [reason, setReason] = useState("");
  const [taskStatus, setTaskStatus] = useState("");
  const [date, setDate] = useState("");
  const [resolution, setResolution] = useState("");
  const [selectedBlockId, setSelectedBlockId] = useState("");
  const [editing, setEditing] = useState<Resource | null>(null);
  const [pending, setPending] = useState<Operation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const taskLive = useQuery({ queryKey: ["task", task.id], queryFn: () => api<Resource>(`/tasks/${task.id}`) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<Resource>("/settings") });
  const steps = useQuery({ queryKey: ["steps", task.id], queryFn: () => api<Resource[]>(`/tasks/${task.id}/steps`) });
  const blocks = useQuery({ queryKey: ["plan-blocks"], queryFn: () => api<Resource[]>("/plan-blocks") });
  const stepId = step?.id ?? block?.data.step_id;
  const summary = useQuery({
    queryKey: ["execution-summary", task.id, stepId ?? "task"],
    queryFn: () => api<ExecutionSummary>(`/tasks/${task.id}/execution-summary${stepId ? `?step_id=${encodeURIComponent(stepId)}` : ""}`),
  });
  const history = useQuery({ queryKey: ["executions", task.id], queryFn: () => api<Resource[]>(`/tasks/${task.id}/executions`) });
  const currentStep = steps.data?.find(s => s.id === stepId);
  const selectedId = block?.id || selectedBlockId;
  const currentBlock = blocks.data?.find(b => b.id === selectedId);
  const availableBlocks = blocks.data?.filter(b => b.data.step_id === stepId) ?? [];
  const timezone = settings.data?.data.timezone;
  const localDate = timezone ? new Date().toLocaleDateString("en-CA", { timeZone: timezone }) : "";
  const rows = history.data?.filter(r => (!stepId || r.data.step_id === stepId) && (!block || r.data.plan_block_id === block.id || r.data.covered_plan_block_ids?.includes(block.id))) ?? [];
  const activeRows = rows.filter(r => summary.data?.effective_record_ids.includes(r.id));
  const hasBlockFeedback = !!block && activeRows.length > 0;
  const locked = busy || !!pending;
  const ready = !!(taskLive.data && timezone && summary.data && history.data && steps.data && blocks.data && (!stepId || currentStep) && (!selectedId || currentBlock));
  const needsCoverage = !editing && (!!summary.data?.unresolved_legacy_minutes || (!selectedId && (availableBlocks.length > 0 || !!summary.data?.legacy_estimated_minutes)));

  function edit(record: Resource) {
    setEditing(record); setMinutes(String(record.data.actual_minutes));
    setFeedback(record.data.feedback); setReason(record.data.unfinished_reason ?? "");
    setTaskStatus(""); setError(""); setMessage("");
  }

  async function save() {
    if (busy) return;
    setError(""); setMessage("");
    let operation = pending;
    if (!operation) {
      const actual = Number(minutes);
      if (!minutes.trim() || !Number.isInteger(actual) || actual < 0 || actual > 100000) {
        setError("请填写0至100000之间的整数分钟；不填写表示尚未反馈。"); return;
      }
      if (!taskLive.data || !timezone || !summary.data || (stepId && !currentStep) || (block && !currentBlock)) {
        setError("资料尚未读完，请稍后重试。"); return;
      }
      const payload: Record<string, unknown> = {
        task_revision: taskLive.data.revision, actual_minutes: actual,
        feedback, unfinished_reason: reason || null, task_status: taskStatus || null,
      };
      const path = editing ? `/executions/${editing.id}/corrections` : "/executions";
      if (editing) payload.revision = editing.revision;
      else Object.assign(payload, {
        task_id: task.id, step_id: stepId ?? null, step_revision: currentStep?.revision ?? null,
        plan_block_id: currentBlock?.id ?? null, plan_block_revision: currentBlock?.revision ?? null,
        performed_on: date || localDate, timezone, legacy_resolution: resolution || null,
      });
      operation = newExecutionOperation(path, payload);
      operation.body.client_operation_id = operation.executionId;
      if (!editing) operation.body.execution_id = operation.executionId;
      setPending(operation);
    }
    setBusy(true);
    try {
      await api(operation.path, { method: "POST", headers: { "Idempotency-Key": operation.idempotencyKey }, body: JSON.stringify(operation.body) });
      setPending(null); setMinutes(""); setEditing(null); setTaskStatus(""); setSelectedBlockId(""); setResolution("");
      setMessage("执行反馈已保存；计划时长和任务完成分别保留。");
      await q.invalidateQueries();
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        setPending(null);
        if (e.status === 409) await q.invalidateQueries();
      }
      setError(String(e));
    } finally { setBusy(false); }
  }

  const blockActual = activeRows.length && activeRows.every(r => r.data.plan_block_id || r.data.covered_plan_block_ids?.length === 1) ? activeRows.reduce((sum, r) => sum + r.data.actual_minutes, 0) : null;
  const display = summary.data ? executionDisplay(block ? { actual_minutes: blockActual, legacy_estimated_minutes: 0 } : summary.data) : null;
  return <section className="execution-feedback" aria-label={block ? "本次安排执行反馈" : "步骤执行反馈"}>
    <h4>实际执行与反馈</h4>
    {block && <p>本次计划：{Math.round((Date.parse(block.data.ends_at) - Date.parse(block.data.starts_at)) / 60000)} 分钟</p>}
    {display && <><p>{display.actualLabel}</p>{display.estimateLabel && <p>{display.estimateLabel}</p>}</>}
    {block && summary.data?.actual_minutes != null && summary.data.actual_minutes !== blockActual && <p>该步骤累计已记录实际：{summary.data.actual_minutes} 分钟</p>}
    {block && !!summary.data?.legacy_estimated_minutes && <p>该步骤另有历史估算：{summary.data.legacy_estimated_minutes} 分钟</p>}
    {summary.data?.unknown_step_ids.length ? <p>仍有未反馈步骤；缺记录保持未知。</p> : null}
    {(summary.error || history.error || taskLive.error || steps.error || blocks.error || settings.error) && <p role="alert">执行资料读取失败，请刷新后重试。</p>}
    {editing && <p>正在更正 {editing.data.actual_minutes} 分钟；原记录会保留。</p>}
    {(!hasBlockFeedback || editing) && <>
      {!block && !editing && availableBlocks.length > 0 && <label>对应的学习安排<select value={selectedBlockId} disabled={locked} onChange={e => { setSelectedBlockId(e.target.value); setResolution(""); }}>
        <option value="">不指定单次安排（需核对覆盖关系）</option>
        {availableBlocks.map(b => <option key={b.id} value={b.id}>{new Date(b.data.starts_at).toLocaleString("zh-CN", {timeZone: timezone || "Asia/Shanghai"})} · {Math.round((Date.parse(b.data.ends_at) - Date.parse(b.data.starts_at))/60000)}分钟</option>)}
      </select></label>}
      <div className="grid2">
        <label>实际分钟<input type="number" min="0" max="100000" step="1" value={minutes} disabled={locked} onChange={e => setMinutes(e.target.value)} /></label>
        {!editing && <label>执行日期<input type="date" value={date || localDate} max={localDate} disabled={locked || !timezone} onChange={e => setDate(e.target.value)} /></label>}
        <label>本次执行结果<select value={feedback} disabled={locked} onChange={e => setFeedback(e.target.value)}>
          <option value="partial">做了一部分</option><option value="completed">本次执行已完成</option><option value="not_started">未执行</option><option value="skipped">主动跳过</option>
        </select></label>
        <label>未完成原因（可不填）<select value={reason} disabled={locked} onChange={e => setReason(e.target.value)}>
          <option value="">不记录原因</option><option value="interrupted">被打断</option><option value="insufficient_time">时间不够</option><option value="unsuitable_schedule">安排不合适</option><option value="skipped">主动跳过</option><option value="other">其他</option>
        </select></label>
        <label>整项任务状态<select value={taskStatus} disabled={locked} onChange={e => setTaskStatus(e.target.value)}>
          <option value="">保持当前状态</option><option value="open">任务仍未完成</option><option value="completed">确认整项任务完成</option>
        </select></label>
      </div>
      {needsCoverage && <label>当前安排及旧估算与本次投入的关系<select value={resolution} disabled={locked} onChange={e => setResolution(e.target.value)}>
        <option value="">请确认覆盖范围</option><option value="replace">本次实际覆盖所选范围的旧估算（未指定单次时覆盖当前全部安排）</option><option value="separate">本次是另一段投入，保留原有安排及估算</option>
      </select></label>}
      <Button type="button" variant="outline" disabled={busy || !ready} onClick={save}>{busy ? "正在保存…" : pending ? "重试保存执行反馈" : editing ? "保存更正" : "保存执行反馈"}</Button>
      {editing && !locked && <Button type="button" variant="outline" onClick={() => { setEditing(null); setMinutes(""); }}>取消更正</Button>}
    </>}
    {pending && !busy && <p>保存结果尚未确认。重试会使用同一次操作，避免重复累计。</p>}
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {rows.length > 0 && <details><summary>执行与更正历史（{rows.length}条）</summary>
      {rows.map(r => <div className="step" key={r.id}>
        <p>{r.data.performed_on} · 手工补记 {r.data.actual_minutes} 分钟{summary.data?.effective_record_ids.includes(r.id) ? " · 当前有效" : " · 已被更正"}</p>
        {r.data.supersedes_id && <p>更正了此前记录，原值保留。</p>}
        {summary.data?.effective_record_ids.includes(r.id) && <Button type="button" variant="outline" disabled={locked} onClick={() => edit(r)}>更正此记录</Button>}
      </div>)}
    </details>}
  </section>;
}
