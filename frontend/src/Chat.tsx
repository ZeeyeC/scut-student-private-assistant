import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  ComposerPrimitive,
  type AppendMessage,
} from "@assistant-ui/react";
import { api } from "./api";
import { applyMessage, type ChatMessage as Message } from "./chat-messages";
import { replayEvents, type PublicEvent } from "./sse";
import type { Resource } from "./types";
import { Button } from "./components/ui/button";
import { DraftReview } from "./DraftReview";
import { visibleDrafts } from "./drafts";
const labels: Record<string, string> = {
  get_current_time: "核对当前日期",
  get_student_context: "读取学习设置",
  start_timetable_import: "请求打开教务",
  get_timetable_import_status: "查询导入进度",
  list_course_occurrences: "查询课程",
  list_tasks: "查询作业",
  create_assignment_draft: "生成任务草稿",
  list_assignment_drafts: "查询待校对草稿",
  set_assignment_draft_deadline: "修改草稿日期",
  resolve_academic_deadline: "推算截止日期",
  create_calendar_event_draft: "生成日程草稿",
  list_calendar_events: "查询日程安排",
  propose_decomposition: "提出拆解",
  propose_daily_plan: "计算每日计划",
  commit_import: "确认保存",
  commit_plan: "确认保存计划",
  set_task_status: "更新作业状态",
  set_task_deadline: "更新截止时间",
};
export function ChatPage({ embedded = false, focusThreadId, focusRequest = 0 }: { embedded?: boolean; focusThreadId?: string; focusRequest?: number }) {
  const q = useQueryClient(),
    [threadId, setThreadId] = useState(focusThreadId ?? ""),
    [runId, setRunId] = useState(""),
    [messages, setMessages] = useState<Message[]>([]),
    [running, setRunning] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState(""),
    [approvalId, setApprovalId] = useState(""),
    [epoch, setEpoch] = useState(0);
  const cursors = useRef<Record<string, number>>({});
  const threads = useQuery({
    queryKey: ["threads"],
    queryFn: () => api<Resource[]>("/agent/threads"),
  });
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  useEffect(() => {
    if (!focusThreadId) return;
    setMessages([]); setRunId(""); setApprovalId(""); setStatus(""); setError(""); setRunning(false);
    cursors.current = {};
    setThreadId(focusThreadId); setEpoch(value => value + 1);
  }, [focusThreadId, focusRequest]);
  useEffect(() => {
    if (focusThreadId) document.querySelector(".review-panel")?.scrollIntoView({ block: "start" });
  }, [focusThreadId, focusRequest, approvalId, drafts.data]);
  const apply = (event: PublicEvent) => {
    if (event.seq <= (cursors.current[event.run_id] ?? 0)) return;
    cursors.current[event.run_id] = event.seq;
    const p = event.payload;
    if (event.type === "message" || event.type === "message_delta") {
      setMessages((messages) => applyMessage(messages, event));
      if (event.type === "message_delta") setStatus("正在回复…");
    }
    if (event.type === "tool_started") setStatus(labels[p.name] ?? "处理请求");
    if (event.type === "draft_ready")
      q.invalidateQueries({ queryKey: ["drafts"] });
    if (event.type === "browser_action_required")
      void api<Resource>("/browser-imports/" + p.id)
        .then((session) => {
          if (session.data.status === "queued")
            window.dispatchEvent(
              new CustomEvent("campus-agent-import", { detail: session }),
            );
        })
        .catch((e) => setError(String(e)));
    if (event.type === "approval_required") {
      setApprovalId(p.approval_id);
      setRunning(false);
      setStatus("等待你的确认");
    }
    if (event.type === "done") {
      setRunning(false);
      setStatus("");
      setApprovalId("");
      q.invalidateQueries();
    }
    if (event.type === "error") {
      setRunning(false);
      setApprovalId("");
      setError(p.message);
    }
  };
  useEffect(() => {
    if (!threadId && threads.data?.length) setThreadId(threads.data.at(-1)!.id);
  }, [threads.data, threadId]);
  useEffect(() => {
    if (!threadId) return;
    const abort = new AbortController();
    (async () => {
      const runs = await api<Resource[]>(`/agent/threads/${threadId}/runs`, { signal: abort.signal });
      if (abort.signal.aborted) return;
      for (const r of runs) {
        if (abort.signal.aborted) return;
        const active = ["queued", "running", "resume_queued", "waiting_approval"].includes(r.data.status);
        if (active) {
          setRunId(r.id);
          setRunning(r.data.status !== "waiting_approval");
        }
        await replayEvents(
          r.id,
          cursors.current[r.id] ?? 0,
          event => { if (!abort.signal.aborted) apply(event); },
          abort.signal,
        );
        if (active) {
          // The run may have finished while history was replaying.
          const latest = await api<Resource>(`/agent/runs/${r.id}`, { signal: abort.signal });
          if (abort.signal.aborted) return;
          setRunning(["queued", "running", "resume_queued"].includes(latest.data.status));
          setApprovalId(latest.data.status === "waiting_approval" ? latest.data.approval_id ?? "" : "");
          if (latest.data.status === "failed") setError(latest.data.error);
        }
      }
    })().catch((e) => {
      if (!abort.signal.aborted) setError(String(e));
    });
    return () => abort.abort();
  }, [threadId, epoch]);
  useEffect(() => {
    if (!runId) return;
    const abort = new AbortController();
    replayEvents(runId, cursors.current[runId] ?? 0, apply, abort.signal).catch(
      (e) => {
        if (!abort.signal.aborted) {
          setError(String(e));
          setRunning(false);
        }
      },
    );
    return () => abort.abort();
  }, [runId, epoch]);
  const runtime = useExternalStoreRuntime<Message>({
    messages,
    isRunning: running,
    convertMessage: (m) => ({
      id: m.id,
      role: m.role,
      content: [{ type: "text", text: m.content }],
    }),
    onNew: async (message: AppendMessage) => {
      const text = message.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("\n");
      if (!text.trim()) return;
      setError("");
      setRunning(true);
      try {
        let tid = threadId;
        if (!tid) {
          const t = await api<Resource>("/agent/threads", {
            method: "POST",
            body: "{}",
          });
          tid = t.id;
          setThreadId(tid);
        }
        const r = await api<Resource>("/agent/runs", {
          method: "POST",
          body: JSON.stringify({ thread_id: tid, message: text }),
        });
        setRunId(r.id);
      } catch (e) {
        setError(String(e));
        setRunning(false);
      }
    },
  });
  const pendingDrafts = visibleDrafts(drafts.data).filter(d => !embedded || ["calendar_event", "assignment"].includes(d.data.draft_kind));
  const hasReview = !!approvalId || pendingDrafts.length > 0;
  return (
    <div className={embedded ? "assistant-page embedded" : "assistant-page"}>
      <header className="chat-toolbar">
        <div>
          <h1>{embedded ? "用 AI 安排事项" : "学习助手"}</h1>
          <p>直接说任务、日程和日期，草稿校对后保存。</p>
        </div>
        <Button
          variant="outline"
          disabled={running}
          onClick={async () => {
            const t = await api<Resource>("/agent/threads", {
              method: "POST",
              body: "{}",
            });
            setThreadId(t.id);
            setRunId("");
            setApprovalId("");
            setError("");
            setStatus("");
            setMessages([]);
            cursors.current = {};
            q.invalidateQueries({ queryKey: ["threads"] });
          }}
        >
          新会话
        </Button>
      </header>
      <div className={hasReview ? "assistant-layout has-review" : "assistant-layout"}>
        <div className="chat-area">
      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root className="chat card">
          <ThreadPrimitive.Viewport className="chat-viewport">
            <ThreadPrimitive.Empty>
              <p>告诉我你想先处理什么，例如“明天有什么课”或“帮我加一个阅读文献的任务”。</p>
              <p className="chat-example">也可以说“第14周之前完成 C++ 大作业”，或“把草稿截止改成明晚8点”。</p>
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages
              components={{
                UserMessage: UserMessage,
                AssistantMessage: AssistantMessage,
              }}
            />
            <ThreadPrimitive.ViewportFooter className="chat-scroll-anchor">
              <ThreadPrimitive.ScrollToBottom className="chat-scroll-to-bottom" behavior="smooth">
                <span aria-hidden="true">↓</span> 回到最新消息
              </ThreadPrimitive.ScrollToBottom>
            </ThreadPrimitive.ViewportFooter>
          </ThreadPrimitive.Viewport>
          <p role="status">{status}</p>
          <ComposerPrimitive.Root className="composer">
            <ComposerPrimitive.Input
              placeholder="输入你的问题…"
              aria-label="给助手的消息"
            />
            <ComposerPrimitive.Send disabled={!!approvalId}>
              发送
            </ComposerPrimitive.Send>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>
      {error && (
        <div role="alert">
          <p>{error}</p>
          <Button
            variant="outline"
            onClick={() => {
              setError("");
              setEpoch((e) => e + 1);
            }}
          >
            重新连接历史
          </Button>
        </div>
      )}
        </div>
      {hasReview && <div className="review-panel" role="complementary" aria-label="草稿校对区">
      <h2 className="review-panel-title">待校对 · {pendingDrafts.length + (approvalId ? 1 : 0)}</h2>
      {approvalId && (
        <ApprovalCard
          id={approvalId}
          runId={runId}
          onResume={() => {
            setApprovalId("");
            setRunning(true);
            setEpoch((e) => e + 1);
          }}
        />
      )}
      {pendingDrafts.map((d) => (
        <DraftReview draft={d} key={d.id} />
      ))}
      </div>}
      </div>
    </div>
  );
}
function UserMessage() {
  return (
    <MessagePrimitive.Root className="message user">
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}
function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="message assistant">
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}
function ApprovalCard({
  id,
  runId,
  onResume,
}: {
  id: string;
  runId: string;
  onResume: () => void;
}) {
  const q = useQueryClient(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const a = useQuery({
    queryKey: ["approval", id],
    queryFn: () => api<Resource>("/agent/approvals/" + id),
    refetchInterval: 15000,
  });
  const decide = async (decision: "approve" | "reject") => {
    if (!a.data) return;
    setBusy(true);
    try {
      await api(`/agent/runs/${runId}/resume`, {
        method: "POST",
        body: JSON.stringify({
          approval_id: id,
          revision: a.data.revision,
          decision,
        }),
      });
      q.invalidateQueries();
      onResume();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card confirm">
      <h2>这一步需要你确认</h2>
      <p>批准后才会保存或更新；拒绝不会写入业务数据。</p>
      {a.data && Date.parse(a.data.data.expires_at) < Date.now() && (
        <p role="alert">此确认已过期，请拒绝后重新提出请求。</p>
      )}
      {a.data?.data.actions.map((action: Record<string, any>, i: number) => (
        <div key={i}>
          <h3>{labels[action.name]}</h3>
          {action.args.draft_id ? (
            <ApprovalDraft id={action.args.draft_id} />
          ) : (
            <ApprovalTask args={action.args} name={action.name} />
          )}
        </div>
      ))}
      <Button
        disabled={
          busy || !a.data || Date.parse(a.data.data.expires_at) < Date.now()
        }
        onClick={() => decide("approve")}
      >
        批准并执行
      </Button>
      <Button
        variant="outline"
        disabled={busy || !a.data}
        onClick={() => decide("reject")}
      >
        拒绝
      </Button>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
function ApprovalDraft({ id }: { id: string }) {
  const d = useQuery({
    queryKey: ["approval-draft", id],
    queryFn: () => api<Resource>("/drafts/" + id),
  });
  if (d.error) return <p role="alert">{String(d.error)}</p>;
  if (!d.data) return <p>正在读取准确内容…</p>;
  const p = d.data.data.payload;
  return (
    <div>
      {p.starts_at && <p>{p.title} · {new Date(p.starts_at).toLocaleString("zh-CN")}–{new Date(p.ends_at).toLocaleString("zh-CN")}</p>}
      {p.items?.map((x: Record<string, any>, i: number) => (
        <p key={i}>
          {x.title} ·{" "}
          {x.due_at
            ? new Date(x.due_at).toLocaleString("zh-CN")
            : "截止时间待确认"}
          <br />
          {x.requirements.join("；")}
        </p>
      ))}
      {p.courses?.map((c: Record<string, any>, i: number) => (
        <p key={i}>
          {c.name} · 星期{c.weekday} · 第 {c.weeks.join(",")} 周 · 第{" "}
          {c.periods.join(",")} 节 · {c.location}
        </p>
      ))}
      {p.steps?.map((s: Record<string, any>, i: number) => (
        <p key={i}>
          {s.title} · 预计 {s.estimated_minutes} 分钟 ·{" "}
          {s.acceptance_criteria.join("；")}
        </p>
      ))}
      {p.blocks?.map((b: Record<string, any>) => (
        <p key={b.id}>
          <strong>{b.title ?? "学习安排"}</strong> ·{" "}
          {new Date(b.starts_at).toLocaleString("zh-CN", {
            timeZone: p.timezone ?? "Asia/Shanghai",
          })}
          –
          {new Date(b.ends_at).toLocaleTimeString("zh-CN", {
            timeZone: p.timezone ?? "Asia/Shanghai",
          })}
          {b.locked ? " · 已锁定" : ""}
        </p>
      ))}
      {p.warnings?.map((w: string, i: number) => (
        <p role="alert" key={i}>
          {w}
        </p>
      ))}
      {p.removed_blocks?.map((b: Record<string, any>) => (
        <p key={b.id}>
          移除旧建议：{b.title} · {b.reason}
        </p>
      ))}
      {p.unscheduled?.map((u: Record<string, any>, i: number) => (
        <p key={i}>
          {u.title}：{u.remaining_minutes == null ? "" : `未安排 ${u.remaining_minutes} 分钟 · `}{u.reason}
        </p>
      ))}
    </div>
  );
}
function ApprovalTask({ args, name }: { args: Record<string, any>; name: string }) {
  const task = useQuery({
    queryKey: ["approval-task", args.task_id],
    queryFn: () => api<Resource>("/tasks/" + args.task_id),
  });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Resource>("/settings"),
  });
  const timezone = settings.data?.data.timezone ?? "Asia/Shanghai";
  function deadline(value: string | null | undefined) {
    if (!value) return "待确认";
    if (Number.isNaN(Date.parse(value))) return "时间无效，请拒绝后重新设置";
    return new Date(value).toLocaleString("zh-CN", {timeZone: timezone, hour12: false});
  }
  if (name === "set_task_deadline") {
    const recovery = args.deadline_type === "remedy_due_at";
    return <div>
      <p>{task.data?.data.title ?? "正在读取待办…"} · 版本 {args.revision}</p>
      <p>原{recovery ? "补救" : ""}截止时间：{deadline(task.data?.data[args.deadline_type])}</p>
      <p>新{recovery ? "补救" : ""}截止时间：{deadline(args.due_at)}</p>
      <p>时区：{timezone}</p>
      {!recovery && task.data?.data.remedy_due_at && <p>确认后清除原补救截止时间：{deadline(task.data.data.remedy_due_at)}</p>}
      <p>已有步骤和学习安排保留；旧计划与拆解草稿会失效，请重新生成。</p>
      {task.data && task.data.revision !== args.revision && <p role="alert">待办已变更，请拒绝这次操作后重新提出请求。</p>}
      {task.error && <p role="alert">{String(task.error)}</p>}
    </div>;
  }
  return (
    <p>
      {task.data?.data.title ?? "正在读取作业…"} · 版本 {args.revision} ·
      将状态改为{" "}
      {args.status === "completed"
        ? "已完成"
        : args.status === "archived"
          ? "已归档"
          : "进行中"}
      {task.error && <span role="alert">{String(task.error)}</span>}
    </p>
  );
}
