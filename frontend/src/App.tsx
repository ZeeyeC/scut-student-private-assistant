import { lazy, Suspense, useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { TodayPage } from "./Today";
import { Settings } from "./Settings";
import { LocalEntry } from "./LocalMode";
import { BrowserImport, stopBrowserImports } from "./BrowserImport";
import { AfterClassCheckin } from "./AfterClass";
import {TimerHeartbeat} from "./ExecutionTimer";
import {Goals} from "./Goals";
import {WeeklyReview} from "./WeeklyReview";
import {NegotiationPanel} from "./NegotiationPanel";
import {DurationSuggestions} from "./DurationSuggestions";
import {TaskDetail} from "./TaskDetail";
import type {Resource} from "./types";
import {ProactiveSuggestions} from "./ProactiveSuggestions";
import {AppShell} from "./layout/AppShell";
import {navigationFromEvent, nextNavigation, type NavigationState, type NavigationTarget} from "./layout/navigation";
const CalendarPage = lazy(() =>
  import("./Calendar").then((m) => ({ default: m.CalendarPage })),
);
const ChatPage = lazy(() =>
  import("./Chat").then((m) => ({ default: m.ChatPage })),
);

export default function App() {
  const mode = useQuery({
    queryKey: ["app-mode"],
    queryFn: () => api<{ mode: string }>("/app-mode"),
  });
  if (mode.isPending)
    return (
      <p className="p-8" role="status">
        正在连接本机助手…
      </p>
    );
  if (mode.error)
    return (
      <main className="auth">
        <h1>暂时无法连接助手</h1>
        <p role="alert">{String(mode.error)}</p>
        <Button onClick={() => location.reload()}>重新连接</Button>
      </main>
    );
  return mode.data.mode === "local" ? (
    <LocalEntry>
      <Workspace local />
    </LocalEntry>
  ) : (
    <Workspace />
  );
}
function Workspace({ local = false }: { local?: boolean }) {
  const q = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<{ id: string; email: string }>("/me"),
  });
  const [error, setError] = useState("");
  const [register, setRegister] = useState(false);
  const [navigation, setNavigation] = useState<NavigationState>({page:'today',request:0});
  const {page,focusDate:calendarDate,threadId:reviewThread,request:reviewRequest}=navigation;
  const go = (target:NavigationTarget) => setNavigation(previous=>nextNavigation(previous,target));
  const [suggestedTask,setSuggestedTask] = useState<string|null>(null);
  useEffect(() => {
    const refresh = () => { void q.invalidateQueries(); };
    window.addEventListener("campus-task-updated", refresh);
    return () => window.removeEventListener("campus-task-updated", refresh);
  }, [q]);
  useEffect(() => {
    const listener = (event: Event) => {
      const target=navigationFromEvent(event.type,(event as CustomEvent).detail);
      if(target) {setNavigation(previous=>nextNavigation(previous,target));if(target.taskId)setSuggestedTask(target.taskId);}
    };
    window.addEventListener("campus-timetable-focus", listener);
    window.addEventListener("campus-navigate", listener);
    window.addEventListener("campus-calendar-saved", listener);
    window.addEventListener("campus-pet-review", listener);
    return () => {
      window.removeEventListener("campus-timetable-focus", listener);
      window.removeEventListener("campus-navigate", listener);
      window.removeEventListener("campus-calendar-saved", listener);
      window.removeEventListener("campus-pet-review", listener);
    };
  }, []);
  const form = useForm<{ email: string; password: string }>();
  if (me.isPending) return <p className="p-8">正在连接助手…</p>;
  if (!me.data && local)
    return (
      <main className="auth">
        <p role="alert">本机会话连接失败，请重新打开助手。</p>
        <Button onClick={() => location.reload()}>重新连接</Button>
      </main>
    );
  if (!me.data)
    return (
      <main className="auth">
        <div className="brand">
          课间
        </div>
        <h1>登录</h1>
        <form
          onSubmit={form.handleSubmit(async (v) => {
            try {
              setError("");
              if (register)
                await api("/auth/register", {
                  method: "POST",
                  body: JSON.stringify(v),
                });
              await api("/auth/login", {
                method: "POST",
                body: new URLSearchParams({
                  username: v.email,
                  password: v.password,
                }),
              });
              await q.invalidateQueries({ queryKey: ["me"] });
            } catch (e) {
              setError(String(e));
            }
          })}
        >
          <label>
            邮箱
            <input
              type="email"
              autoComplete="username"
              {...form.register("email", { required: true })}
            />
          </label>
          <label>
            密码
            <input
              type="password"
              minLength={12}
              autoComplete={register ? "new-password" : "current-password"}
              {...form.register("password", { required: true })}
            />
          </label>
          {error && <p role="alert">{error}</p>}
          <Button disabled={form.formState.isSubmitting}>
            {register ? "注册并登录" : "登录"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => setRegister(!register)}
          >
            {register ? "已有账号" : "创建账号"}
          </Button>
        </form>
      </main>
    );
  return (
    <AppShell page={page} onNavigate={go} footer={!local && <>
            <small>{me.data.email}</small>
            <Button
              variant="outline"
              onClick={async () => {
                await stopBrowserImports(me.data!.id);
                await api("/auth/logout", { method: "POST" });
                q.clear();
              }}
            >
              退出登录
            </Button>
          </>}>
        <AfterClassCheckin />
        <TimerHeartbeat />
        <ProactiveSuggestions onOpenTask={id=>{setSuggestedTask(id);go({page:'tasks',taskId:id});}} />
        {suggestedTask&&<SuggestedTask id={suggestedTask} onClose={()=>setSuggestedTask(null)}/>}
        <BrowserImport showOverview={page === "calendar"} />
        <Suspense fallback={<p role="status">正在加载页面…</p>}>
          {page === "today" ? (
            <TodayPage />
          ) : page === "calendar" ? (
            <CalendarPage key="calendar" focusDate={calendarDate} />
          ) : page === "tasks" ? (
            <><h1>任务</h1><div className="workspace-tabs" role="group" aria-label="任务分类">{(['todo','goals','review'] as const).map((tab,i)=><button key={tab} aria-pressed={(navigation.taskTab??'todo')===tab} onClick={()=>go({page:'tasks',taskTab:tab})}>{['待办','目标','复盘'][i]}</button>)}</div>
            {navigation.taskTab==='goals'?<Goals/>:navigation.taskTab==='review'?<><DurationSuggestions/><WeeklyReview/><NegotiationPanel/></>:<CalendarPage key="schedule" mode="schedule"/>}</>
          ) : page === "assistant" ? (
            <ChatPage focusThreadId={reviewThread} focusRequest={reviewRequest} />
          ) : (
            <Settings local={local} />
          )}
        </Suspense>
    </AppShell>
  );
}

function SuggestedTask({id,onClose}:{id:string;onClose:()=>void}) {
  const task=useQuery({queryKey:["task",id],queryFn:()=>api<Resource>(`/tasks/${id}`)});
  useEffect(()=>{if(task.data)document.getElementById("suggested-task")?.scrollIntoView({block:"start"});},[id,task.data?.id]);
  return <section id="suggested-task" className="card" aria-label="建议关联的任务详情">
    <h2>{task.data?.data.title??"关联任务"}</h2><Button variant="outline" onClick={onClose}>关闭关联任务详情</Button>
    {task.isPending&&<p role="status">正在读取任务…</p>}{task.error&&<p role="alert">{String(task.error)}</p>}
    {task.data&&<TaskDetail key={id} task={task.data}/>}
  </section>;
}
