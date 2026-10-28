import {useEffect, useRef, useState} from "react";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {api, ApiError} from "./api";
import type {Resource} from "./types";
import {Button} from "./components/ui/button";
import {newExecutionOperation} from "./execution-state";
import {formatElapsed, serializeTimerAction, timerElapsed} from "./timer-state";

type Pending = ReturnType<typeof newExecutionOperation<Record<string, unknown>>>;
const open = (r: Resource) => !["finished", "discarded"].includes(r.data.status);

export function TimerHeartbeat() {
  const q = useQueryClient();
  const timers = useQuery({queryKey:["execution-timers"], queryFn:()=>api<Resource[]>("/execution-timers"), refetchInterval:5000});
  const running = timers.data?.find(r=>r.data.status === "running");
  useEffect(()=>{
    if (!running) return;
    const id = running.id;
    const interval = setInterval(()=>{
      void serializeTimerAction(id, async()=>{
        const latest = (await api<Resource[]>("/execution-timers")).find(r=>r.id === id);
        if (!latest || latest.data.status !== "running") return;
        await api(`/execution-timers/${id}/actions`, {method:"POST",body:JSON.stringify({revision:latest.revision,client_operation_id:crypto.randomUUID(),action:"heartbeat"})});
        await q.invalidateQueries({queryKey:["execution-timers"]});
      }).catch(()=>{void q.invalidateQueries({queryKey:["execution-timers"]});});
    },15000);
    return ()=>clearInterval(interval);
  },[running?.id,running?.data.status,q]);
  return null;
}

export function ExecutionTimer({task, step, block, ready=true, legacyResolution=null}: {task: Resource; step?: Resource; block?: Resource; ready?: boolean; legacyResolution?: string|null}) {
  const q=useQueryClient();
  const timers=useQuery({queryKey:["execution-timers"],queryFn:()=>api<Resource[]>("/execution-timers")});
  const [busy,setBusy]=useState(false), [error,setError]=useState(""), [pending,setPending]=useState<Pending|null>(null);
  const [feedback,setFeedback]=useState("partial"), [reason,setReason]=useState(""), [taskStatus,setTaskStatus]=useState("");
  const [manual,setManual]=useState(false), [minutes,setMinutes]=useState("");
  const [tick,setTick]=useState(Date.now());
  const list=(timers.data??[]).filter(r=>r.data.task_id===task.id && r.data.step_id === (step?.id ?? block?.data.step_id ?? null) && (!block || r.data.target.plan_block_id===block.id));
  const current=list.find(open);
  const retained=useRef<Resource|null>(null);
  if (current) retained.current=current;
  const timer=current ?? (pending ? retained.current : null);
  const anchor=useRef({seconds:0,received:Date.now()});
  useEffect(()=>{if(timer) anchor.current={seconds:timer.data.elapsed_seconds,received:Date.now()};},[timer,timers.dataUpdatedAt]);
  useEffect(()=>{const interval=setInterval(()=>setTick(Date.now()),1000);return()=>clearInterval(interval);},[]);

  async function submit(action: string) {
    if (busy) return;
    setBusy(true);setError("");
    try {
      const result=await serializeTimerAction(timer?.id ?? "start",async()=>{
        let operation=pending;
        if(!operation) {
          if(action === "start") {
            const [t,s,blocks,settings] = await Promise.all([
              api<Resource>(`/tasks/${task.id}`),api<Resource[]>(`/tasks/${task.id}/steps`),api<Resource[]>("/plan-blocks"),api<Resource>("/settings"),
            ]);
            const targetStep=s.find(r=>r.id === (step?.id??block?.data.step_id));
            const targetBlock=blocks.find(r=>r.id===block?.id);
            const payload:Record<string,unknown>={task_id:task.id,task_revision:t.revision,step_id:targetStep?.id??null,step_revision:targetStep?.revision??null,plan_block_id:targetBlock?.id??null,plan_block_revision:targetBlock?.revision??null,timezone:settings.data.timezone,performed_on:new Date().toLocaleDateString("en-CA",{timeZone:settings.data.timezone}),legacy_resolution:legacyResolution};
            operation=newExecutionOperation("/execution-timers",payload);
            operation.body.client_operation_id=operation.executionId;
            operation.body.execution_id=operation.executionId;
          } else {
            const latest=(await api<Resource[]>("/execution-timers")).find(r=>r.id===timer?.id);
            if(!latest) throw new Error("计时记录已变化，请刷新。");
            const payload:Record<string,unknown>={revision:latest.revision,client_operation_id:crypto.randomUUID(),action};
            if(action === "finish") {
              Object.assign(payload,{feedback,unfinished_reason:reason||null,task_status:taskStatus||null});
              if(taskStatus) payload.task_revision=(await api<Resource>(`/tasks/${task.id}`)).revision;
              if(manual) {
                if(!minutes.trim() || !Number.isInteger(Number(minutes)) || Number(minutes)<0 || Number(minutes)>100000) throw new Error("补记实际分钟需要0至100000的整数。");
                payload.actual_minutes=Number(minutes);
              }
            }
            operation=newExecutionOperation(`/execution-timers/${latest.id}/actions`,payload);
          }
          setPending(operation);
        }
        return api<Resource>(operation.path,{method:"POST",headers:{"Idempotency-Key":operation.idempotencyKey},body:JSON.stringify(operation.body)});
      });
      retained.current=result;
      setPending(null);setManual(false);setMinutes("");
      await q.invalidateQueries();
    } catch(e) {
      if(e instanceof ApiError && e.status<500) {setPending(null);await q.invalidateQueries();}
      setError(String(e));
    } finally {setBusy(false);}
  }

  const seconds=timer?timerElapsed({status:timer.data.status,elapsed_seconds:anchor.current.seconds},anchor.current.received,tick):0;
  return <section aria-label="自愿计时" className="execution-timer">
    <h4>自愿计时</h4>
    {!timer && !pending && <><p>开始后才记录投入；保持助手连接，失联超过2分钟的未确认时段可事后补记。</p><Button type="button" variant="outline" disabled={busy||!ready||timers.isPending} onClick={()=>submit("start")}>开始计时</Button></>}
    {timer && <>
      <p role="timer">{formatElapsed(seconds)} · {({running:"计时中",paused:"已暂停",interrupted:"连接中断，等待核对",finished:"已结束",discarded:"已放弃"} as Record<string,string>)[timer.data.status]}</p>
      {timer.data.status === "interrupted" && <p>仅保留最后已确认的投入，未自动计算离线时间。可以继续、结束或改为补记。</p>}
      {timer.data.status === "running" ? <Button type="button" variant="outline" disabled={busy||!!pending} onClick={()=>submit("pause")}>暂停计时</Button> : open(timer) && <Button type="button" variant="outline" disabled={busy||!!pending} onClick={()=>submit("resume")}>继续计时</Button>}
      {open(timer) && <>
        <label>计时结束结果<select value={feedback} disabled={busy||!!pending} onChange={e=>setFeedback(e.target.value)}><option value="partial">做了一部分，任务未必完成</option><option value="completed">本次执行已完成</option><option value="not_started">未执行</option><option value="skipped">主动跳过</option></select></label>
        <label>计时未完成原因<select value={reason} disabled={busy||!!pending} onChange={e=>setReason(e.target.value)}><option value="">不记录原因</option><option value="interrupted">被打断</option><option value="insufficient_time">时间不够</option><option value="unsuitable_schedule">安排不合适</option><option value="skipped">主动跳过</option><option value="other">其他</option></select></label>
        <label>计时后的任务状态<select value={taskStatus} disabled={busy||!!pending} onChange={e=>setTaskStatus(e.target.value)}><option value="">保持当前状态</option><option value="open">任务仍未完成</option><option value="completed">确认整项任务完成</option></select></label>
        <label><input type="checkbox" checked={manual} disabled={busy||!!pending} onChange={e=>setManual(e.target.checked)}/>改为手工补记，替代本次计时投入</label>
        {manual && <label>补记实际分钟<input type="number" min="0" max="100000" value={minutes} disabled={busy||!!pending} onChange={e=>setMinutes(e.target.value)}/></label>}
        <Button type="button" disabled={busy||!!pending} onClick={()=>submit("finish")}>结束并保存反馈</Button>
        <Button type="button" variant="outline" disabled={busy||!!pending} onClick={()=>submit("discard")}>放弃本次计时</Button>
      </>}
    </>}
    {pending && !busy && <><p>操作结果尚未确认，重试不会重复记录。</p><Button type="button" onClick={()=>submit("retry")}>重试计时操作</Button></>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
