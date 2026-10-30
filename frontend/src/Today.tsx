import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Resource } from "./types";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { DraftActions } from "./Assignments";
import {TaskCard} from "./Assignments";
import {DetailPanel} from "./layout/DetailPanel";
import {selectTodayTasks} from "./layout/today-workspace";
import {SmartSchedule} from "./SmartSchedule";
import { navigate, visibleDrafts } from "./drafts";
import type { ScheduleEvent } from "./schedule";
import { ExecutionFeedback } from "./ExecutionFeedback";
import type { CourseIntervalsData } from "./schedule";
import { CourseIntervals } from "./CourseIntervals";
import {PageHeader} from './layout/PageHeader';
import {TaskSummaryRow,taskCourse,useTaskEstimates} from './TaskSummary';
import {ArrowUpRight,Plus,Play} from 'lucide-react';
const clock = (v: string, tz = "Asia/Shanghai") =>
  new Date(v).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
  });
export function TodayPage() {
  const [panel,setPanel]=useState<'plan'|'records'|'focus'|null>(null);
  const tasks=useQuery({queryKey:['tasks'],queryFn:()=>api<Resource[]>('/tasks')});
  const blocks=useQuery({queryKey:['plan-blocks'],queryFn:()=>api<Resource[]>('/plan-blocks')});
  const settings=useQuery({queryKey:['settings'],queryFn:()=>api<Resource>('/settings')});
  const courses=useQuery({queryKey:['courses'],queryFn:()=>api<Resource[]>('/courses')});
  const tz=settings.data?.data.timezone??'Asia/Shanghai',now=new Date();
  const localDate=now.toLocaleDateString('en-CA',{timeZone:tz});
  const agenda=useQuery({queryKey:['today-events',localDate,tz],queryFn:()=>api<{events:ScheduleEvent[];warnings:string[]}>(`/calendar-events?start=${localDate}&end=${localDate}`)});
  const {next,block}=selectTodayTasks(tasks.data??[],blocks.data??[],now,tz);
  const shownOthers=(tasks.data??[]).filter(t=>t.data.status==='open'&&t.id!==next?.id).slice(0,3);
  const estimates=useTaskEstimates([...(next?[next]:[]),...shownOthers]);
  const openTask=(id:string)=>window.dispatchEvent(new CustomEvent('campus-navigate',{detail:{page:'tasks',taskId:id}}));
  const allTasks=()=>window.dispatchEvent(new CustomEvent('campus-navigate',{detail:{page:'tasks'}}));
  const events=(agenda.data?.events??[]).filter(event=>event.kind!=='scheduling_constraint');
  const nextEvent=events.find(e=>Date.parse(e.ends_at)>now.getTime());
  const course=(task:Resource)=>taskCourse(task,courses.data??[]);
  return <>
    <PageHeader title="今日" meta={`${now.toLocaleDateString('zh-CN',{month:'long',day:'numeric',timeZone:tz})} · ${now.toLocaleDateString('zh-CN',{weekday:'short',timeZone:tz})}`}><Button variant="outline" onClick={()=>setPanel('plan')}>安排今天</Button></PageHeader>
    {tasks.error&&<p role="alert">{String(tasks.error)}</p>}{blocks.error&&<p role="alert">{String(blocks.error)}</p>}
    <div className="today-workspace"><section aria-label="接下来">{tasks.isPending?<p role="status">正在读取任务…</p>:next?<div className="next-task"><div className="next-task-top"><span>接下来</span>{block&&<time>{clock(block.data.starts_at,tz)}</time>}</div><h2><button type="button" onClick={()=>openTask(next.id)}>{next.data.title}</button></h2><p className="next-task-meta">{block?`${clock(block.data.starts_at,tz)}–${clock(block.data.ends_at,tz)}　·　${Math.round((Date.parse(block.data.ends_at)-Date.parse(block.data.starts_at))/60000)} 分钟`:'尚未安排时间'}</p><div className="next-task-bottom"><small>{course(next)}</small><Button onClick={()=>setPanel('focus')}><Play size={16}/>开始专注</Button></div></div>:<p>暂无待办任务。</p>}
      <div className="today-other-tasks"><div className="workspace-section-head"><h2>其他待办<small>{(tasks.data??[]).filter(t=>t.data.status==='open'&&t.id!==next?.id).length}</small></h2><button type="button" className="workspace-text-button" onClick={allTasks}>全部任务<ArrowUpRight size={16}/></button></div>{shownOthers.map(task=><TaskSummaryRow key={task.id} task={task} course={course(task)} minutes={estimates.get(task.id)??null} timezone={tz} onOpen={()=>openTask(task.id)}/>)}<button type="button" className="workspace-text-button today-add-task" onClick={()=>{allTasks();window.dispatchEvent(new Event('campus-new-task'));}}><Plus size={16}/>添加任务</button></div>
    </section><section className="today-agenda" aria-label="今日安排"><div className="workspace-section-head"><h2>今日安排</h2><button type="button" className="workspace-text-button" onClick={()=>window.dispatchEvent(new CustomEvent('campus-navigate',{detail:{page:'calendar'}}))}>查看日程</button></div>{agenda.isPending&&<p role="status">正在读取安排…</p>}{agenda.error&&<p role="alert">{String(agenda.error)}</p>}{agenda.data?.warnings.map((warning,i)=><p role="alert" key={i}>{warning}</p>)}
      {events.map(event=><button type="button" className={`today-agenda-row${event.id===nextEvent?.id?' active':''}`} key={event.id} onClick={()=>window.dispatchEvent(new CustomEvent('campus-calendar-saved',{detail:event.starts_at}))}><time>{clock(event.starts_at,tz)}</time><span className="agenda-marker" aria-hidden="true"/><span className="agenda-text"><strong>{event.title}</strong><small>{event.kind==='course'?`${event.location?event.location+' · ':''}${clock(event.starts_at,tz)}–${clock(event.ends_at,tz)}`:event.id===nextEvent?.id?`${clock(event.starts_at,tz)}–${clock(event.ends_at,tz)}`:`${Math.round((Date.parse(event.ends_at)-Date.parse(event.starts_at))/60000)} 分钟`}</small></span></button>)}
      {agenda.data&&!agenda.data.events.length&&<p>今天暂无安排。</p>}
    </section></div>
    <div className="today-record-actions"><button type="button" className="workspace-text-button" onClick={()=>setPanel('records')}>执行与记录</button><button type="button" className="workspace-text-button" onClick={()=>window.dispatchEvent(new CustomEvent('campus-after-class-open',{detail:{manual:true}}))}>课后作业</button></div>
    <DetailPanel open={panel==='plan'} title="安排学习" onClose={()=>setPanel(null)}><SmartSchedule/></DetailPanel>
    <DetailPanel open={panel==='records'} title="执行与记录" onClose={()=>setPanel(null)}><TodayExecutionDetails/></DetailPanel>
    <DetailPanel open={panel==='focus'} title={next?.data.title??'专注'} onClose={()=>setPanel(null)}>{next&&<>{block&&<ExecutionFeedback task={next} block={block}/>}<TaskCard task={next} expanded/></>}</DetailPanel>
  </>;
}
function TodayExecutionDetails() {
  const q = useQueryClient(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const blocks = useQuery({
    queryKey: ["plan-blocks"],
    queryFn: () => api<Resource[]>("/plan-blocks"),
  });
  const tasks = useQuery({
    queryKey: ["tasks"],
    queryFn: () => api<Resource[]>("/tasks"),
  });
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Resource>("/settings"),
  });
  const tz = settings.data?.data.timezone ?? "Asia/Shanghai";
  const localDate = new Date().toLocaleDateString("en-CA", { timeZone: tz });
  const courses = useQuery({
    queryKey: ["today-courses", localDate, tz],
    queryFn: () =>
      api<
        (CourseIntervalsData & {
          id: string;
          title: string;
          starts_at: string;
          ends_at: string;
          location: string;
        })[]
      >(`/occurrences?start=${localDate}&end=${localDate}`),
  });
  const events = useQuery({queryKey:["today-events",localDate,tz],queryFn:()=>api<{events:ScheduleEvent[]; warnings:string[]}>(`/calendar-events?start=${localDate}&end=${localDate}`)});
  const title = (id: string) =>
    tasks.data?.find((t) => t.id === id)?.data.title ?? "学习任务";
  const today = (blocks.data ?? []).filter(
    (b) =>
      new Date(b.data.starts_at).toLocaleDateString("en-CA", {
        timeZone: tz,
      }) === localDate,
  );
  return (
    <>
      <div className="page-head">
        <div>
          <h2>执行与记录</h2>
          <p>
            {new Date().toLocaleDateString("zh-CN", {
              month: "long",
              day: "numeric",
              weekday: "long",
              timeZone: tz,
            })}{" "}
          </p>
        </div>
        <Button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await api("/plan-drafts", {
                method: "POST",
                body: JSON.stringify({ scope: "today" }),
              });
              q.invalidateQueries({ queryKey: ["drafts"] });
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "正在计算…" : "一键生成当日日程"}
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
      <section className="card"><h2>课后作业</h2><p>当天课程结束、达到设置的等待时间后，打开奶娃时一起记下各门课的作业。</p>
        <Button variant="outline" onClick={() => window.dispatchEvent(new CustomEvent("campus-after-class-open", { detail: { manual: true } }))}>查看课后作业询问</Button>
      </section>
      <div className="grid2">
        <section className="card">
          <h2>今日课程</h2>
          {courses.isPending && <p role="status">正在加载课程…</p>}
          {courses.error && <p role="alert">{String(courses.error)}</p>}
          {courses.data?.length === 0 && <p>今天没有课程。</p>}
          {courses.data?.map((c) => (
            <div className="step" key={c.id}>
              <strong>
                {clock(c.starts_at, tz)}–{clock(c.ends_at, tz)}
              </strong>
              <h3>{c.title}</h3>
              <p>{c.location}</p>
              <CourseIntervals event={c} timezone={tz} />
            </div>
          ))}
        </section>
        <section className="card">
          <h2>今日学习安排</h2>
          {blocks.isPending && <p role="status">正在加载安排…</p>}
          {blocks.error && <p role="alert">{String(blocks.error)}</p>}
          {today.length === 0 && (
            <p>还没有安排。先添加作业步骤，再生成计划草稿。</p>
          )}
          {today.map((b) => (
            <div className="step" key={b.id}>
              <strong>
                {clock(b.data.starts_at, tz)}–{clock(b.data.ends_at, tz)}
              </strong>
              <h3>{title(b.data.task_id)}</h3>
              <p>
                {b.data.status === "completed"
                  ? b.data.execution_record_id ? "本次执行已反馈" : "已按计划时长记录估算投入"
                  : b.data.locked
                    ? "时间已锁定"
                    : "建议时间"}
              </p>
              <Button
                variant="outline"
                disabled={b.data.status === "completed"}
                onClick={async () => {
                  try {
                    await api("/plan-blocks/" + b.id, {
                      method: "PATCH",
                      body: JSON.stringify({
                        revision: b.revision,
                        completed: true,
                      }),
                    });
                    q.invalidateQueries();
                  } catch (e) {
                    setError(String(e));
                  }
                }}
              >
                按计划时长记录估算
              </Button>
              {tasks.data?.find(t => t.id === b.data.task_id) && <ExecutionFeedback task={tasks.data.find(t => t.id === b.data.task_id)!} block={b} />}
              <Button
                variant="outline"
                onClick={async () => {
                  try {
                    await api("/plan-blocks/" + b.id, {
                      method: "PATCH",
                      body: JSON.stringify({
                        revision: b.revision,
                        locked: !b.data.locked,
                      }),
                    });
                    q.invalidateQueries();
                  } catch (e) {
                    setError(String(e));
                  }
                }}
              >
                {b.data.locked ? "解锁" : "锁定时间"}
              </Button>
            </div>
          ))}
        </section>
      </div>
      <section className="card">
        <h2>今日固定事项</h2>
        {events.error && <p role="alert">{String(events.error)}</p>}
        {events.data?.events.filter(e=>e.kind === "fixed_event").length === 0 && <p>今天没有固定事项。</p>}
        {events.data?.events.filter(e=>e.kind === "fixed_event").map(e=><div key={e.id} className="step"><strong>{clock(e.starts_at,tz)}–{clock(e.ends_at,tz)}</strong><h3>{e.title}</h3></div>)}
        <Button variant="outline" onClick={()=>navigate("作业")}>去待办与日程添加事项</Button>
      </section>
      {visibleDrafts(drafts.data)
        .filter((d) => d.data.draft_kind === "plan")
        .map((d) => (
          <PlanReview draft={d} key={d.id} />
        ))}

    </>
  );
}
export function PlanReview({ draft }: { draft: Resource }) {
  const [error, setError] = useState("");
  const p = draft.data.payload;
  const displayedBlocks = p.scope === "today" ? p.blocks.filter((b: Record<string, any>) =>
    new Date(b.starts_at).toLocaleDateString("en-CA", {timeZone: p.timezone}) === p.target_date
  ) : p.blocks;
  return (
    <section className="card" aria-label="计划草稿">
      <p className="eyebrow">程序计算 · {p.blocks.length > 0 || p.removed_blocks?.length > 0 ? "等待确认" : "无新增学习安排"}</p>
      <h2>{p.scope === "today" ? `${p.target_date} 当日日程` : `未来 ${p.horizon_days} 天计划`}</h2>
      <p>
        课程、固定事项、已确认禁排、锁定时间和依赖已纳入计算。更改设置后可重新生成。
      </p>
      {p.scope === "today" && <p>按 {p.timezone} 计算今天剩余时间。已开始、已完成、锁定及其他日期的安排保留；其他日期不在下方展开。排不下的工作会列出，不自动延至明天。</p>}
      {p.changes && <p>新增 {p.changes.added_ids.length} 项 · 保留 {p.changes.retained_ids.length} 项 · 替换或移除 {p.changes.removed_ids.length} 项。确认前正式日程保持原样。</p>}
      {p.protected_windows?.length > 0 && <div><h3>本次避让的禁排时段</h3>{p.protected_windows.map((r: Resource) => <p key={r.id}>{r.data.title} · {new Date(r.data.starts_at).toLocaleString("zh-CN", {timeZone: p.timezone})} 至 {new Date(r.data.ends_at).toLocaleString("zh-CN", {timeZone: p.timezone})}</p>)}</div>}
      {p.warnings?.map((w: string, i: number) => (
        <p role="alert" key={i}>
          {w}
        </p>
      ))}
      {p.removed_blocks?.length > 0 && (
        <div>
          <h3>确认后移除失效的旧建议</h3>
          {p.removed_blocks.map((b: Record<string, any>) => (
            <p key={b.id}>
              {b.title} · {b.reason}
            </p>
          ))}
        </div>
      )}
      {p.fixed_agenda?.length > 0 && <div>
        <h3>已固定的课程与事项</h3>
        <p>这些安排已经保存，规划学习时间会避让它们。</p>
        {p.fixed_agenda.map((e: Record<string, any>, i: number)=><p key={i}>{new Date(e.starts_at).toLocaleDateString("zh-CN",{timeZone:p.timezone})} {clock(e.starts_at,p.timezone)}–{clock(e.ends_at,p.timezone)} · {e.title}</p>)}
      </div>}
      {!displayedBlocks.length && <p>本次没有生成学习时间块。{p.unscheduled.length ? "请先处理下方未安排事项，再重新规划。" : "当前没有需要新安排的步骤；如仍有待办，请核对预计耗时、拆解与完成状态。"}</p>}
      {displayedBlocks.map((b: Record<string, any>) => (
        <div className="step" key={b.id}>
          <strong>
            {new Date(b.starts_at).toLocaleDateString("zh-CN", {
              timeZone: p.timezone ?? "Asia/Shanghai",
            })}{" "}
            {clock(b.starts_at, p.timezone)}–{clock(b.ends_at, p.timezone)}
          </strong>
          <h3>{b.title ?? "学习安排"}</h3>
          <p>
            {b.locked ? "保留锁定安排" : "学习时间块"} ·{" "}
            {b.status === "completed" ? "已完成" : "待执行"}
          </p>
          {b.explanation?.reasons?.map((reason: string, i: number) => <p key={i}>{reason}</p>)}
        </div>
      ))}
      {p.unscheduled.length > 0 && (
        <div role="alert">
          <h3>仍未安排</h3>
          {p.unscheduled.map((u: Record<string, any>, i: number) => (
            <p key={i}>
              <strong>{u.title || "待完成步骤"}</strong>{u.remaining_minutes == null ? "" : `：还剩 ${u.remaining_minutes} 分钟，`}
              <span>{u.reason}</span>
            </p>
          ))}
        </div>
      )}
      {p.unscheduled.length > 0 && <Button variant="outline" onClick={()=>navigate("作业")}>补充耗时或拆解步骤</Button>}
      <DraftActions draft={draft} payload={p} onError={setError} canSave={p.blocks.length > 0 || p.removed_blocks?.length > 0} />
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
