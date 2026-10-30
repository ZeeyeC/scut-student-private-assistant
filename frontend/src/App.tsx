import { lazy, Suspense, useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { TodayPage } from "./Today";
import { Settings } from "./Settings";
import { LocalEntry } from "./LocalMode";
import { stopBrowserImports } from "./BrowserImport";
import {TimetableImportHost} from "./TimetableImportPanel";
import {ReminderLinkPanel} from "./ReminderLinkPanel";
import { AfterClassCheckin } from "./AfterClass";
import {TimerHeartbeat} from "./ExecutionTimer";
import {TasksPage} from "./TasksPage";
import {ReviewInbox} from "./ReviewInbox";
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
  const [createTaskRequested,setCreateTaskRequested]=useState(false);
  const [navigation, setNavigation] = useState<NavigationState>({page:'today',request:0});
  const {page,focusDate:calendarDate,threadId:reviewThread,request:reviewRequest}=navigation;
  const go = (target:NavigationTarget) => setNavigation(previous=>nextNavigation(previous,target));
  useEffect(() => {
    const refresh = () => { void q.invalidateQueries(); };
    window.addEventListener("campus-task-updated", refresh);
    return () => window.removeEventListener("campus-task-updated", refresh);
  }, [q]);
  useEffect(() => {
    const listener = (event: Event) => {
      const target=navigationFromEvent(event.type,(event as CustomEvent).detail);
      if(target) setNavigation(previous=>nextNavigation(previous,target));
    };
    window.addEventListener("campus-timetable-focus", listener);
    window.addEventListener("campus-navigate", listener);
    window.addEventListener("campus-calendar-saved", listener);
    window.addEventListener("campus-pet-review", listener);
    const createTask=()=>{setCreateTaskRequested(true);setNavigation(previous=>nextNavigation(previous,{page:'tasks'}));};
    window.addEventListener('campus-new-task',createTask);
    return () => {
      window.removeEventListener("campus-timetable-focus", listener);
      window.removeEventListener("campus-navigate", listener);
      window.removeEventListener("campus-calendar-saved", listener);
      window.removeEventListener("campus-pet-review", listener);
      window.removeEventListener('campus-new-task',createTask);
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
        <ReviewInbox onOpenTask={id=>go({page:'tasks',taskId:id})}>
        <TimetableImportHost/>
        <ReminderLinkPanel/>
        <Suspense fallback={<p role="status">正在加载页面…</p>}>
          {page === "today" ? (
            <TodayPage />
          ) : page === "calendar" ? (
            <CalendarPage key="calendar" focusDate={calendarDate} filter={navigation.calendarFilter} focusRequest={navigation.request}/>
          ) : page === "tasks" ? (
            <TasksPage tab={navigation.taskTab} onTab={taskTab=>go({page:'tasks',taskTab})} taskId={navigation.taskId} focusRequest={navigation.request} createRequested={createTaskRequested} onCreateHandled={()=>setCreateTaskRequested(false)}/>
          ) : page === "assistant" ? (
            <ChatPage focusThreadId={reviewThread} focusRequest={reviewRequest} />
          ) : (
            <Settings local={local} />
          )}
        </Suspense>
        </ReviewInbox>
    </AppShell>
  );
}
