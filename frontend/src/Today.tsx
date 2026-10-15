import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Resource } from "./types";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { DraftActions } from "./Assignments";
import { TodoList } from "./TodoList";
import { navigate, visibleDrafts } from "./drafts";
import type { ScheduleEvent } from "./schedule";
const clock = (v: string, tz = "Asia/Shanghai") =>
  new Date(v).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
  });
export function TodayPage() {
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
        {
          id: string;
          title: string;
          starts_at: string;
          ends_at: string;
          location: string;
        }[]
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
          <p className="eyebrow">A LITTLE PROGRESS, EVERY DAY</p>
          <h1>今天，专注几件事。</h1>
          <p>
            {new Date().toLocaleDateString("zh-CN", {
              month: "long",
              day: "numeric",
              weekday: "long",
              timeZone: tz,
            })}{" "}
            · 给学习留出确定的时间
          </p>
        </div>
        <Button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api("/plan-drafts", {
                method: "POST",
                body: JSON.stringify({ horizon_days: 7 }),
              });
              q.invalidateQueries({ queryKey: ["drafts"] });
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "正在计算…" : "规划未来 7 天"}
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
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
                  ? "已记录本次投入"
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
                记录本次完成
              </Button>
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
        <Button variant="outline" onClick={()=>navigate("课表")}>去课表添加事项</Button>
      </section>
      <TodoList />
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
  return (
    <section className="card">
      <p className="eyebrow">程序计算 · {p.blocks.length > 0 || p.removed_blocks?.length > 0 ? "等待确认" : "无新增学习安排"}</p>
      <h2>未来 {p.horizon_days} 天计划</h2>
      <p>
        课程、固定事项、锁定时间和依赖已纳入计算。更改学习设置后可重新生成。
      </p>
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
      {!p.blocks.length && <p>本次没有生成学习时间块。{p.unscheduled.length ? "请先处理下方未安排事项，再重新规划。" : "当前没有需要新安排的步骤；如仍有待办，请核对预计耗时、拆解与完成状态。"}</p>}
      {p.blocks.map((b: Record<string, any>) => (
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
