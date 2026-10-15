import { lazy, Suspense, useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { AssignmentsPage } from "./Assignments";
import { TodayPage } from "./Today";
import { Settings } from "./Settings";
import { LocalEntry } from "./LocalMode";
import { BrowserImport, stopBrowserImports } from "./BrowserImport";
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
  const [page, setPage] = useState("今日");
  const [calendarDate, setCalendarDate] = useState<string>();
  useEffect(() => {
    const listener = (event: Event) => {
      const page = (event as CustomEvent<string>).detail;
      if (["今日", "课表", "作业", "助手", "设置"].includes(page)) {setCalendarDate(undefined); setPage(page);}
    };
    const saved = (event: Event) => {
      setCalendarDate((event as CustomEvent<string>).detail);
      setPage("课表");
    };
    window.addEventListener("campus-navigate", listener);
    window.addEventListener("campus-calendar-saved", saved);
    return () => {
      window.removeEventListener("campus-navigate", listener);
      window.removeEventListener("campus-calendar-saved", saved);
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
          课间 <span>Campus companion</span>
        </div>
        <h1>把课业，安排得从容一点。</h1>
        <p>你的课表、作业和每天的学习安排，集中在这里。</p>
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
    <div className="shell">
      <aside>
        <div className="brand">
          课间<span>Campus companion</span>
        </div>
        <nav>
          {["今日", "课表", "作业", "助手", "设置"].map((n) => (
            <Button
              key={n}
              variant={page === n ? "default" : "outline"}
              onClick={() => {setCalendarDate(undefined); setPage(n);}}
            >
              {n === "作业" ? "待办 / 作业" : n}
            </Button>
          ))}
        </nav>
        <small>{local ? "本机个人助手 · 数据保存在本机" : me.data.email}</small>
        {!local && (
          <>
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
          </>
        )}
      </aside>
      <main className={page === "助手" ? "assistant-main" : undefined}>
        <BrowserImport showOverview={page === "课表"} />
        <Suspense fallback={<p role="status">正在加载页面…</p>}>
          {page === "今日" ? (
            <TodayPage />
          ) : page === "课表" ? (
            <CalendarPage focusDate={calendarDate} />
          ) : page === "作业" ? (
            <AssignmentsPage />
          ) : page === "助手" ? (
            <ChatPage />
          ) : (
            <Settings local={local} />
          )}
        </Suspense>
      </main>
    </div>
  );
}
