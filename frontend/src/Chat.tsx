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
import { AgentApproval } from "./AgentApproval";
import { ConstraintIntents } from "./ConstraintIntents";
import { visibleDrafts } from "./drafts";
import {PageHeader} from './layout/PageHeader';
import {DetailPanel} from './layout/DetailPanel';
import {ArrowUp} from 'lucide-react';
import {useChatImage,ImageDropArea,ChatImageControls} from './chat-images';
import {scrollWithinWorkspace} from './layout/scrollWithin';
const labels: Record<string, string> = {
  get_current_time: "核对当前日期",
  get_student_context: "读取学习设置",
  start_timetable_import: "请求打开教务",
  get_timetable_import_status: "查询导入进度",
  list_course_occurrences: "查询课程",
  create_timetable_draft: "生成文字课表草稿",
  list_timetable_drafts: "查询待校对课表",
  update_timetable_draft: "补充课程信息",
  list_tasks: "查询作业",
  create_assignment_draft: "生成任务草稿",
  list_assignment_drafts: "查询待校对草稿",
  set_assignment_draft_deadline: "修改草稿日期",
  resolve_academic_deadline: "推算截止日期",
  create_calendar_event_draft: "生成日程草稿",
  list_calendar_events: "查询日程安排",
  propose_decomposition: "提出拆解",
  propose_daily_plan: "计算每日计划",
  list_constraint_intents: "查询原约束意图",
  propose_constraint_intent: "记录待补充约束",
  update_constraint_intent: "补充原约束意图",
  prepare_constraint_intent: "生成待校对约束",
  cancel_constraint_intent: "取消约束意图",
  get_planning_context: "核对真实风险与容量",
  list_planning_intents: "查询协商历史",
  propose_planning_intent: "记录规划意向",
  update_planning_intent: "继续修改本轮协商",
  preview_planning_intent: "计算真实可选方案",
  preview_draft_conflicts: "核对草稿冲突",
  commit_import: "确认保存",
  commit_plan: "确认保存计划",
  set_task_status: "更新作业状态",
  set_task_deadline: "更新截止时间",
};
export function ChatPage({ embedded = false, courseEntry = false, reviewOutside=false, focusThreadId, focusRequest = 0 }: { embedded?: boolean; courseEntry?: boolean; reviewOutside?:boolean;focusThreadId?: string; focusRequest?: number }) {
  const q = useQueryClient(),
    [threadId, setThreadId] = useState(focusThreadId ?? ""),
    [runId, setRunId] = useState(""),
    [messages, setMessages] = useState<Message[]>([]),
    [running, setRunning] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState(""),
    [approvalId, setApprovalId] = useState(""),
    [epoch, setEpoch] = useState(0),
    [showConstraints,setShowConstraints] = useState(false);
  const [historyOpen,setHistoryOpen]=useState(false);
  const image = useChatImage();
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const [imageRun,setImageRun]=useState<Resource|null>(null);
  const currentThread=useRef(threadId);currentThread.current=threadId;
  const cursors = useRef<Record<string, number>>({});
  const threads = useQuery({
    queryKey: ["threads"],
    queryFn: () => api<Resource[]>("/agent/threads"),
  });
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  const constraintIntents = useQuery({queryKey:["constraint-intents"], queryFn:()=>api<Resource[]>("/constraint-intents")});
  const activeRun=useRef("");
  useEffect(() => {
    if (!focusThreadId) return;
    image.clear();setImageRun(null);activeRun.current='';setMessages([]); setRunId(""); setApprovalId(""); setStatus(""); setError(""); setRunning(false);
    cursors.current = {};
    setThreadId(focusThreadId); setEpoch(value => value + 1);
  }, [focusThreadId, focusRequest]);
  useEffect(() => {
    if (focusThreadId) scrollWithinWorkspace(document.querySelector(".review-panel"));
  }, [focusThreadId, focusRequest, approvalId, drafts.data]);
  // History and the live stream may finish in different orders. Only the
  // currently owned run may change the composer's busy/approval state.
  const syncRun=(run:Resource)=>{
    if(run.data.attachment && run.data.thread_id===currentThread.current)setImageRun(run);
    if(activeRun.current!==run.id)return;
    setRunning(["queued","running","resume_queued"].includes(run.data.status));
    setApprovalId(run.data.status==='waiting_approval'?run.data.approval_id??'':'');
    if(['done','failed','cancelled'].includes(run.data.status)){activeRun.current='';setStatus('');}
    if(run.data.status==='failed')setError(run.data.error);
  };
  const apply = (event: PublicEvent) => {
    const ownsRun=activeRun.current===event.run_id;
    if (event.seq <= (cursors.current[event.run_id] ?? 0)) return;
    cursors.current[event.run_id] = event.seq;
    const p = event.payload;
    if (event.type === "message" || event.type === "message_delta") {
      setMessages((messages) => applyMessage(messages, event));
      if (event.type === "message_delta" && ownsRun) setStatus("正在回复…");
    }
    if (event.type === "cancelled" && ownsRun) {activeRun.current="";setRunning(false);setStatus("已取消识别");}
    if (event.type === "tool_started" && ownsRun) setStatus(labels[p.name] ?? "处理请求");
    if (event.type === "tool_finished") { void q.invalidateQueries({queryKey:["constraint-intents"]}); void q.invalidateQueries({queryKey:["planning-intents"]}); }
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
    if (event.type === "approval_required" && ownsRun) {
      setApprovalId(p.approval_id);
      setRunning(false);
      setStatus("等待你的确认");
    }
    if (event.type === "done") {
      if(ownsRun){activeRun.current='';setRunning(false);setStatus('');setApprovalId('');}
      q.invalidateQueries();
    }
    if (event.type === "error" && ownsRun) {
      activeRun.current="";
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
        if(r.data.attachment&&r.data.thread_id===currentThread.current)setImageRun(r);
        if (abort.signal.aborted) return;
        const active = ["queued", "running", "resume_queued", "waiting_approval"].includes(r.data.status);
        if (active && !activeRun.current) {
          activeRun.current=r.id;
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
          syncRun(latest);
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
    replayEvents(runId, cursors.current[runId] ?? 0, apply, abort.signal).then(async()=>{
      const latest=await api<Resource>(`/agent/runs/${runId}`,{signal:abort.signal});
      if(!abort.signal.aborted)syncRun(latest);
    }).catch(
      (e) => {
        if (!abort.signal.aborted && activeRun.current===runId) {
          activeRun.current="";
          setError(String(e));
          setRunning(false);
        }
      },
    );
    return () => abort.abort();
  }, [runId, epoch]);
  async function sendMessage(text:string){
      if ((!text.trim() && !image.image) || activeRun.current) return;
      const attached=image.image;
      if(attached&&!image.consent){image.setError("请先确认图片识别授权。");return;}
      const reference=image.reference ? new Date(image.reference).toISOString() : undefined;
      text=text.trim() || "识别这张作业截图";
      image.freeze();
      const owner='request:'+crypto.randomUUID();activeRun.current=owner;
      setError("");
      setRunning(true);
      let tid = threadId;
      try {
        if (!tid) {
          const t = await api<Resource>("/agent/threads", {
            method: "POST",
            body: "{}",
            headers: attached ? {"Idempotency-Key":attached.threadKey} : {},
          });
          if(activeRun.current!==owner)return;
          tid = t.id;
          setThreadId(tid);
        }
        if(attached&&!attached.assetId){
          const form=new FormData();form.set("file",attached.file);
          const asset=await api<Resource>("/assets",{method:"POST",body:form,headers:{"Idempotency-Key":attached.uploadKey}});
          attached.assetId=asset.id;
        }
        if(activeRun.current!==owner)return;
        const r = await api<Resource>("/agent/runs", {
          method: "POST",
          body: JSON.stringify({ thread_id: tid, message: text, ...(attached?{attachment:{kind:"assignment_image",asset_id:attached.assetId,consent:true,reference_time:reference}}:{}) }),
          headers:attached?{"Idempotency-Key":attached.runKey}:{},
        });
        if(activeRun.current!==owner)return;
        activeRun.current=r.id;setRunId(r.id);
        if(attached){setImageRun(r);image.clear();runtime.thread.composer.setText("");}
      } catch (e) {
        if(activeRun.current!==owner)return;
        if(attached?.assetId&&tid){
          try{
            const runs=await api<Resource[]>('/agent/threads/'+tid+'/runs');
            const recovered=runs.find(r=>r.data.attachment?.asset_id===attached.assetId);
            if(activeRun.current!==owner)return;
            if(recovered){setImageRun(recovered);setRunId(recovered.id);activeRun.current=recovered.id;syncRun(recovered);image.clear();return;}
          }catch{/* Keep selection and stable operation keys for explicit retry. */}
        }
        activeRun.current='';setError(String(e));
        setRunning(false);
      }
  }
  async function actOnImage(action:'retry'|'cancel'){
    if(!imageRun)return;
    try{
      const latest=await api<Resource>('/agent/runs/'+imageRun.id);
      const r=await api<Resource>('/agent/runs/'+imageRun.id+'/image/'+action,{method:'POST',body:JSON.stringify({revision:latest.revision})});
      setImageRun(r);setError('');
      if(action==='retry'){activeRun.current=r.id;setRunId(r.id);setRunning(true);setEpoch(v=>v+1)}
      else{activeRun.current='';setRunning(false);setStatus('已取消识别');void q.invalidateQueries({queryKey:['drafts']});}
    }catch(e){setError(String(e))}
  }
  const runtime = useExternalStoreRuntime<Message>({
    messages,
    isRunning: running,
    convertMessage: (m) => ({
      id: m.id,
      role: m.role,
      content: [{ type: "text", text: m.content }, ...(m.asset_id?[{type:"image" as const,image:"/api/assets/"+m.asset_id}]:[])],
    }),
    onNew: async (message: AppendMessage) => {
      await sendMessage(message.content.filter(c=>c.type==='text').map(c=>c.text).join('\n'));
    },
  });
  const pendingDrafts = visibleDrafts(drafts.data).filter(d=>!d.data.source?.thread_id || d.data.source.thread_id===threadId).filter(d=>!reviewOutside&&!d.data.source?.constraint_intent_id).filter(d => !embedded || (courseEntry ? ["timetable_text"] : ["calendar_event", "assignment"]).includes(d.data.draft_kind));
  const hasIntents = constraintIntents.data?.some(r=>["clarifying","ready_for_review"].includes(r.data.status));
  useEffect(()=>{if(hasIntents)setShowConstraints(true);},[hasIntents]);
  const hasReview = !!approvalId || pendingDrafts.length > 0 || showConstraints || !!hasIntents;
  return (
    <div className={embedded ? "assistant-page embedded" : "assistant-page"}>
      {!embedded&&<PageHeader title="助手"/>}
      <header className="chat-toolbar">
        <div>
          {embedded?<h1>{courseEntry?'用文字添加课表':'用 AI 安排事项'}</h1>:<span>{threads.data?.find(t=>t.id===threadId)?.data.title??'新会话'}</span>}

        </div>
        <Button
          variant="outline"
          disabled={running}
          onClick={async () => {
            const t = await api<Resource>("/agent/threads", {
              method: "POST",
              body: "{}",
            });
            image.clear();setImageRun(null);activeRun.current='';setThreadId(t.id);
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
        <Button variant="outline" onClick={()=>setShowConstraints(v=>!v)}>{showConstraints?"收起约束入口":"安排持续约束"}</Button>
        {!embedded&&<button type="button" className="workspace-text-button" onClick={()=>setHistoryOpen(true)}>会话记录</button>}
      </header>
      <div className={hasReview ? "assistant-layout has-review" : "assistant-layout"}>
        <div className="chat-area">
      <AssistantRuntimeProvider runtime={runtime}>
        <ImageDropArea disabled={running||!!approvalId} onFiles={files=>void image.add(files)}><ThreadPrimitive.Root className="chat card">
          <ThreadPrimitive.Viewport className="chat-viewport">
            <ThreadPrimitive.Empty>
              <p>想安排什么？</p>


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
          {imageRun&&<div className="image-run-actions" role="status">
            {imageRun.data.status==='failed'&&<button type="button" onClick={()=>void actOnImage('retry')}>重试图片识别</button>}
            {running&&<button type="button" onClick={()=>void actOnImage('cancel')}>取消图片识别</button>}
          </div>}
          <ComposerPrimitive.Root className="composer">
            <ChatImageControls state={image} disabled={running||!!approvalId}/>

            <ComposerPrimitive.Input
              ref={composerInput}
              placeholder="说说你想安排什么"
              aria-label="给助手的消息"
            />
            <div className="composer-bottom"><span/>{image.image?<button type="button" className="workspace-button" aria-label="发送作业截图" disabled={running||!!approvalId||!image.consent} onClick={()=>void sendMessage(composerInput.current?.value??'')}><ArrowUp size={16}/>发送</button>:<ComposerPrimitive.Send className="workspace-button" disabled={!!approvalId}><ArrowUp size={16}/>发送</ComposerPrimitive.Send>}</div>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.Root></ImageDropArea>
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
        <AgentApproval
          id={approvalId}
          runId={runId}
          onResume={() => {
            setApprovalId("");
            setRunning(true);
            setEpoch((e) => e + 1);
          }}
        />
      )}
      {(showConstraints||hasIntents)&&<ConstraintIntents threadId={threadId}/>}
      {pendingDrafts.map((d) => (
        <DraftReview draft={d} key={d.id} />
      ))}
      </div>}
      </div>
      <DetailPanel open={historyOpen} title="会话记录" onClose={()=>setHistoryOpen(false)}>{threads.data?.map(thread=><button type="button" className="thread-history-row" key={thread.id} onClick={()=>{image.clear();setImageRun(null);activeRun.current="";setRunning(false);setStatus("");setThreadId(thread.id);setMessages([]);setRunId('');setApprovalId('');setError('');cursors.current={};setEpoch(v=>v+1);setHistoryOpen(false);}}>{thread.data.title??'会话'}</button>)}</DetailPanel>
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
