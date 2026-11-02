import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  MessagePartPrimitive,
  ComposerPrimitive,
  type AppendMessage,
} from "@assistant-ui/react";
import { api } from "./api";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { applyMessage, messageAssetIds, type ChatMessage as Message } from "./chat-messages";
import { replayEvents, type PublicEvent } from "./sse";
import type { Resource } from "./types";
import { Button } from "./components/ui/button";
import {PendingMemories,useMemoryView} from "./MemoryManager";
import {ChatAssignmentReview} from "./ChatAssignmentReview";
import { DraftReview } from "./DraftReview";
import { AgentApproval } from "./AgentApproval";
import { ConstraintIntents } from "./ConstraintIntents";
import { visibleDrafts } from "./drafts";
import {PageHeader} from './layout/PageHeader';
import {DetailPanel} from './layout/DetailPanel';
import {ArrowUp} from 'lucide-react';
import {useChatImage,ImageDropArea,ChatImageControls} from './chat-images';
import {useChatDocuments,ChatDocumentControls,DOC_ACCEPT,isDocFile} from './chat-documents';
import {KnowledgeManager} from './KnowledgeManager';
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
export function ChatPage({ embedded = false, courseEntry = false, reviewOutside=false, focusThreadId, focusSourceId, focusRequest = 0 }: { embedded?: boolean; courseEntry?: boolean; reviewOutside?:boolean;focusThreadId?: string; focusSourceId?:string; focusRequest?: number }) {
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
  const [navigating,setNavigating]=useState(false);
  const image = useChatImage();
  const documents = useChatDocuments();
  const documentInput = useRef<HTMLInputElement>(null);
  const [knowledgeOpen,setKnowledgeOpen] = useState(false);
  const batchKeys = useRef({signature:"",runKey:"",threadKey:""});
  const sources = useQuery({queryKey:["knowledge-sources"],queryFn:()=>api<{items:Resource[]}>("/knowledge/library?limit=100").then(r=>r.items)});
  const receiveFiles=(files:File[])=>{const docs=files.filter(isDocFile);const images=files.filter(f=>!isDocFile(f));if(docs.length)void documents.add(docs);if(images.length)void image.add(images);};
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const [imageRun,setImageRun]=useState<Resource|null>(null);
  const viewEpoch=useRef(0);
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
  useEffect(()=>{
    if(!focusSourceId)return;
    const abort=new AbortController(), view=viewEpoch.current;
    if(activeRun.current){setError('助手正在处理请求，请结束后再选用资料。');return;}
    api<Resource>('/knowledge/sources/'+encodeURIComponent(focusSourceId),{signal:abort.signal}).then(source=>{
      if(abort.signal.aborted||viewEpoch.current!==view)return;
      if(activeRun.current){setError('助手正在处理请求，资料尚未选用，请稍后重新选择。');return;}
      documents.attachSource(source);
    }).catch(e=>{if(!abort.signal.aborted&&viewEpoch.current===view)setError(String(e));});
    return ()=>abort.abort();
  },[focusSourceId,focusRequest]);
  useEffect(() => {
    if (!focusThreadId) return;
    viewEpoch.current++;setNavigating(false);image.clear();documents.clear();setImageRun(null);activeRun.current='';setMessages([]); setRunId(""); setApprovalId(""); setStatus(""); setError(""); setRunning(false);
    cursors.current = {};
    setThreadId(focusThreadId); setEpoch(value => value + 1);
  }, [focusThreadId, focusRequest]);
  useEffect(() => {
    if (focusThreadId) scrollWithinWorkspace(document.querySelector(".review-panel"));
  }, [focusThreadId, focusRequest, approvalId, drafts.data]);
  // History and the live stream may finish in different orders. Only the
  // currently owned run may change the composer's busy/approval state.
  const syncRun=(run:Resource)=>{
    if((run.data.attachment||run.data.attachments?.length) && run.data.thread_id===currentThread.current)setImageRun(run);
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
    if (event.type === "tool_finished") { void q.invalidateQueries({queryKey:["memories"]}); void q.invalidateQueries({queryKey:["constraint-intents"]}); void q.invalidateQueries({queryKey:["planning-intents"]}); }
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
        if((r.data.attachment||r.data.attachments?.length)&&r.data.thread_id===currentThread.current)setImageRun(r);
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
      if ((!text.trim() && !image.images.length && !documents.totalCount) || activeRun.current || navigating) return;
      const attached=[...image.images], attachedDocs=[...documents.documents], attachedSources=[...documents.selectedSources];
      const hasAttachments=!!(attached.length||attachedDocs.length||attachedSources.length);
      const signature=image.runKey+documents.runKey;
      if(batchKeys.current.signature!==signature)batchKeys.current={signature,runKey:crypto.randomUUID(),threadKey:crypto.randomUUID()};
      const keys={...batchKeys.current};
      let sourceIds:string[]=[];
      text=text.trim() || (documents.totalCount?"总结这些课程资料":attached.length>1?"识别这些作业截图":"识别这张作业截图");
      image.freeze();if(hasAttachments)documents.freeze();
      const owner='request:'+crypto.randomUUID();activeRun.current=owner;
      setError("");
      setRunning(true);
      let tid = threadId;
      try {
        if (!tid) {
          const t = await api<Resource>("/agent/threads", {
            method: "POST",
            body: "{}",
            headers: hasAttachments ? {"Idempotency-Key":keys.threadKey} : {},
          });
          if(activeRun.current!==owner)return;
          tid = t.id;
          setThreadId(tid);
        }
        sourceIds=await documents.onSend(attachedDocs,attachedSources,()=>activeRun.current===owner);
        if(activeRun.current!==owner)return;
        for(const item of attached){
          if(activeRun.current!==owner)return;
          if(!item.assetId){
            const form=new FormData();form.set("file",item.file);
            const asset=await api<Resource>("/assets",{method:"POST",body:form,headers:{"Idempotency-Key":item.uploadKey}});
            item.assetId=asset.id;
          }
        }
        if(activeRun.current!==owner)return;
        const r = await api<Resource>("/agent/runs", {
          method: "POST",
          body: JSON.stringify({ thread_id: tid, message: text, ...(sourceIds.length?{source_ids:sourceIds}:{}), ...(attached.length?{attachments:attached.map(item=>({kind:"assignment_image",asset_id:item.assetId,consent:true}))}:{}) }),
          headers:hasAttachments?{"Idempotency-Key":keys.runKey}:{},
        });
        if(activeRun.current!==owner)return;
        activeRun.current=r.id;setRunId(r.id);
        if(hasAttachments){if(attached.length)setImageRun(r);image.clear();documents.clear();runtime.thread.composer.setText("");void q.invalidateQueries({queryKey:["knowledge-sources"]});}
      } catch (e) {
        if(activeRun.current!==owner)return;
        if(hasAttachments&&attached.every(item=>item.assetId)&&attachedDocs.every(item=>item.sourceId)&&tid){
          try{
            // Replay the exact operation key: reusable sources cannot identify a run.
            const recovered=await api<Resource>('/agent/runs',{method:'POST',headers:{'Idempotency-Key':keys.runKey},body:JSON.stringify({thread_id:tid,message:text,...(sourceIds.length?{source_ids:sourceIds}:{}),...(attached.length?{attachments:attached.map(item=>({kind:'assignment_image',asset_id:item.assetId,consent:true}))}:{})})});
            if(activeRun.current!==owner)return;
            if(recovered){if(attached.length)setImageRun(recovered);setRunId(recovered.id);activeRun.current=recovered.id;syncRun(recovered);image.clear();documents.clear();if(recovered.data.message===text)runtime.thread.composer.setText("");else setError("已恢复原图片消息，新的文字说明请另行发送。");return;}
          }catch{/* Keep selection and stable operation keys for explicit retry. */}
        }
        documents.unfreeze();activeRun.current='';setError(String(e));
        setRunning(false);
      }
  }
  async function actOnImage(action:'retry'|'cancel'){
    if(!imageRun)return;
    const target=imageRun.id, thread=currentThread.current, view=viewEpoch.current;
    try{
      const latest=await api<Resource>('/agent/runs/'+target);
      if(currentThread.current!==thread||viewEpoch.current!==view)return;
      const r=await api<Resource>('/agent/runs/'+target+'/image/'+action,{method:'POST',body:JSON.stringify({revision:latest.revision})});
      if(currentThread.current!==thread||viewEpoch.current!==view)return;
      setImageRun(r);setError('');
      if(action==='retry'){activeRun.current=r.id;setRunId(r.id);setRunning(true);setEpoch(v=>v+1)}
      else{activeRun.current='';setRunning(false);setStatus('已取消识别');void q.invalidateQueries({queryKey:['drafts']});}
    }catch(e){if(currentThread.current===thread&&viewEpoch.current===view)setError(String(e))}
  }
  const runtime = useExternalStoreRuntime<Message>({
    messages,
    isRunning: running,
    convertMessage: (m) => ({
      id: m.id,
      role: m.role,
      content: [{ type: "text", text: m.content + (m.source_ids?.length?"\n附件："+m.source_ids.map(id=>sources.data?.find(s=>s.id===id)?.data.title??"课程资料").join("、"):"") }, ...messageAssetIds(m).map(id=>({type:"image" as const,image:"/api/assets/"+id}))],
    }),
    onNew: async (message: AppendMessage) => {
      await sendMessage(message.content.filter(c=>c.type==='text').map(c=>c.text).join('\n'));
    },
  });
  const allPendingDrafts = visibleDrafts(drafts.data).filter(d=>!d.data.source?.thread_id || d.data.source.thread_id===threadId).filter(d=>!reviewOutside&&!d.data.source?.constraint_intent_id).filter(d => !embedded || (courseEntry ? ["timetable_text"] : ["calendar_event", "assignment"]).includes(d.data.draft_kind));
  const imageDrafts=allPendingDrafts.filter(d=>d.data.draft_kind==='assignment'&&d.data.source?.thread_id===threadId&&(d.data.payload.asset_id||d.data.payload.asset_ids?.length));
  const pendingDrafts=allPendingDrafts.filter(d=>!imageDrafts.some(imageDraft=>imageDraft.id===d.id));
  const memories = useMemoryView();
  const pendingMemoryCount=memories.data?.candidates.filter(c=>c.data.source?.thread_id===threadId).length??0;
  const hasIntents = constraintIntents.data?.some(r=>["clarifying","ready_for_review"].includes(r.data.status));
  useEffect(()=>{if(hasIntents)setShowConstraints(true);},[hasIntents]);
  const hasReview = pendingMemoryCount>0 || !!approvalId || pendingDrafts.length > 0 || showConstraints || !!hasIntents;
  return (
    <div className={embedded ? "assistant-page embedded" : "assistant-page"}>
      <DetailPanel open={knowledgeOpen} title="课程资料" onClose={()=>setKnowledgeOpen(false)}><KnowledgeManager disabled={running||!!approvalId||navigating} onSelect={source=>documents.toggleSource(source)} selectedIds={documents.selectedSources.map(s=>s.id)}/></DetailPanel>
      {!embedded&&<PageHeader title="助手"/>}
      <header className="chat-toolbar">
        <div>
          {embedded?<h1>{courseEntry?'用文字添加课表':'用 AI 安排事项'}</h1>:<span>{threads.data?.find(t=>t.id===threadId)?.data.title??'新会话'}</span>}

        </div>
        <Button
          variant="outline"
          disabled={running||navigating}
          onClick={async () => {
            const view=++viewEpoch.current;
            image.clear();documents.clear();setImageRun(null);activeRun.current='';setNavigating(true);
            setRunId("");setApprovalId("");setError("");setStatus("");setMessages([]);cursors.current={};
            try {
              const t=await api<Resource>("/agent/threads",{method:"POST",body:"{}"});
              if(viewEpoch.current!==view)return;
              setThreadId(t.id);q.invalidateQueries({queryKey:["threads"]});
            } catch(e) {
              if(viewEpoch.current===view){setError("新会话创建失败，请重试："+String(e));setEpoch(v=>v+1);}
            } finally { if(viewEpoch.current===view)setNavigating(false); }

          }}
        >
          新会话
        </Button>
        <Button variant="outline" onClick={()=>setShowConstraints(v=>!v)}>{showConstraints?"收起约束入口":"安排持续约束"}</Button>
        {!embedded&&<button type="button" className="workspace-text-button" onClick={()=>setHistoryOpen(true)}>会话记录</button>}
        {!embedded&&<button type="button" className="workspace-text-button" onClick={()=>setKnowledgeOpen(true)}>选择资料</button>}
      </header>
      <div className={hasReview ? "assistant-layout has-review" : "assistant-layout"}>
        <div className="chat-area">
      <AssistantRuntimeProvider runtime={runtime}>
        <ImageDropArea disabled={running||!!approvalId||navigating} onFiles={receiveFiles}><ThreadPrimitive.Root className="chat card">
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
            {imageDrafts.map(d=><ChatAssignmentReview key={d.id} draft={d} disabled={running||!!approvalId||navigating}/>)}
            <ThreadPrimitive.ViewportFooter className="chat-scroll-anchor">
              <ThreadPrimitive.ScrollToBottom className="chat-scroll-to-bottom" behavior="smooth">
                <span aria-hidden="true">↓</span> 回到最新消息
              </ThreadPrimitive.ScrollToBottom>
            </ThreadPrimitive.ViewportFooter>
          </ThreadPrimitive.Viewport>
          <p role="status">{status}</p>
          {imageRun&&<div className="image-run-actions" role="status">
            {imageRun.data.status==='failed'&&<button type="button" onClick={()=>void actOnImage('retry')}>重试图片识别</button>}
            {running&&imageRun.id===runId&&<button type="button" onClick={()=>void actOnImage('cancel')}>取消图片识别</button>}
          </div>}
          <ComposerPrimitive.Root className="composer">
            <ChatImageControls state={image} disabled={running||!!approvalId||navigating} onPickDocuments={()=>documentInput.current?.click()}/>
            <ChatDocumentControls state={documents} disabled={running||!!approvalId||navigating} onPickFiles={()=>documentInput.current?.click()}/>
            <input ref={documentInput} hidden multiple type="file" accept={DOC_ACCEPT} aria-label="选择课程资料" disabled={running||!!approvalId||navigating} onChange={e=>{if(e.target.files?.length)void documents.add(Array.from(e.target.files));e.target.value="";}}/>

            <ComposerPrimitive.Input
              disabled={navigating}
              ref={composerInput}
              placeholder="说说你想安排什么"
              aria-label="给助手的消息"
            />
            <div className="composer-bottom"><span/>{(image.images.length||documents.totalCount)?<button type="button" className="workspace-button" aria-label="发送" disabled={running||!!approvalId||navigating} onClick={()=>void sendMessage(composerInput.current?.value??'')}><ArrowUp size={16}/>发送</button>:<ComposerPrimitive.Send className="workspace-button" disabled={!!approvalId||navigating}><ArrowUp size={16}/>发送</ComposerPrimitive.Send>}</div>
          </ComposerPrimitive.Root>
          {!!(image.images.length||documents.totalCount)&&<p className="chat-image-disclosure">发送附件的相关内容将交给已配置的模型</p>}
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
      <h2 className="review-panel-title">待校对 · {pendingDrafts.length + pendingMemoryCount + (approvalId ? 1 : 0)}</h2>
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
      {!!pendingMemoryCount&&<PendingMemories threadId={threadId} disabled={running}/>}
      {(showConstraints||hasIntents)&&<ConstraintIntents threadId={threadId}/>}
      {pendingDrafts.map((d) => (
        <DraftReview draft={d} key={d.id} />
      ))}
      </div>}
      </div>
      <DetailPanel open={historyOpen} title="会话记录" onClose={()=>setHistoryOpen(false)}>{threads.data?.map(thread=><button type="button" className="thread-history-row" key={thread.id} onClick={()=>{viewEpoch.current++;setNavigating(false);image.clear();documents.clear();setImageRun(null);activeRun.current="";setRunning(false);setStatus("");setThreadId(thread.id);setMessages([]);setRunId('');setApprovalId('');setError('');cursors.current={};setEpoch(v=>v+1);setHistoryOpen(false);}}>{thread.data.title??'会话'}</button>)}</DetailPanel>
    </div>
  );
}
function UserMessage() {
  return (
    <MessagePrimitive.Root className="message user">
      <MessagePrimitive.Parts components={{Text:PlainMessageText}} />
    </MessagePrimitive.Root>
  );
}
function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="message assistant">
      <MessagePrimitive.Parts components={{Text:AssistantMarkdown}} />
    </MessagePrimitive.Root>
  );
}

function PlainMessageText(){return <MessagePartPrimitive.Text smooth={false}/>;}
