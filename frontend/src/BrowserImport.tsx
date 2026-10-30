import { useEffect, useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Resource } from "./types";
import { api } from "./api";
import { ImportGuide } from "./ImportGuide";
import { DraftReview } from "./DraftReview";
import { Button } from "./components/ui/button";
const nonce = crypto.randomUUID();
export function extension(action: string, payload: unknown = {}): Promise<any> {
  return new Promise((resolve, reject) => {
    const requestId = crypto.randomUUID();
    const timer = setTimeout(() => {
      window.removeEventListener("message", listen);
      reject(new Error("未检测到课表扩展，请先按安装说明加载扩展。"));
    }, 5000);
    const listen = (e: MessageEvent) => {
      if (
        e.source !== window ||
        e.origin !== location.origin ||
        e.data?.channel !== "campus-assistant-reply-v1" ||
        e.data.nonce !== nonce ||
        e.data.requestId !== requestId
      )
        return;
      clearTimeout(timer);
      window.removeEventListener("message", listen);
      e.data.error ? reject(new Error(e.data.error)) : resolve(e.data.result);
    };
    window.addEventListener("message", listen);
    window.postMessage(
      { channel: "campus-assistant-v1", action, nonce, requestId, payload },
      location.origin,
    );
  });
}
const labels: Record<string, string> = {
  queued: "等待扩展回执",
  waiting_login: "教务已打开，请本人登录，找到个人课表并选择学期、点击查询",
  waiting_timetable: "等待课表加载；请选择学期并点击查询",
  extracting: "正在提取课表",
  preview_ready: "已提取，请校对下方草稿",
  completed: "已保存",
  failed: "导入失败",
  cancelled: "已取消",
  expired: "导入已过期",
};
export async function stopBrowserImports(owner: string) {
  const sessions = await api<Resource[]>("/browser-imports");
  await Promise.allSettled(
    sessions.map((s) => extension("stop", { sessionId: s.id, owner })),
  );
}
export function BrowserImport({ showOverview = true }: { showOverview?: boolean }) {
  const q = useQueryClient(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [open, setOpen] = useState(false),
    [phase, setPhase] = useState<"checking" | "missing" | "ready">("checking");
  const pending = useRef<Resource | null>(null);
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  const detect = async () => {
    setPhase("checking");
    setError("");
    try {
      await extension("detect");
      setPhase("ready");
    } catch {
      setPhase("missing");
    }
  };
  const showGuide = () => {
    setOpen(true);
    void detect();
  };
  const lock = useRef(false);
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<{ id: string }>("/me"),
  });
  const sessions = useQuery({
    queryKey: ["browser-imports"],
    queryFn: () => api<Resource[]>("/browser-imports"),
    refetchInterval: 2000,
    refetchIntervalInBackground: true,
  });
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      await extension("detect");
      const existing =
        pending.current ??
        [...(sessions.data ?? [])]
          .reverse()
          .find((b) =>
            [
              "queued",
              "waiting_login",
              "waiting_timetable",
              "extracting",
            ].includes(b.data.status),
          );
      const b =
        existing ??
        (await api<Resource>("/browser-imports", {
          method: "POST",
          body: JSON.stringify({ school_id: "scut" }),
        }));
      await extension("start", {
        sessionId: b.id,
        owner: me.data!.id,
        expiresAt: b.data.expires_at,
      });
      pending.current = null;
      await q.invalidateQueries({ queryKey: ["browser-imports"] });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      void q.invalidateQueries({ queryKey: ["browser-imports"] });
    }
  };
  useEffect(() => {
    window.addEventListener("campus-start-import", showGuide);
    return () => window.removeEventListener("campus-start-import", showGuide);
  });
  useEffect(() => {
    const listener = (event: Event) => {
      pending.current = (event as CustomEvent<Resource>).detail;
      showGuide();
      void q.invalidateQueries({ queryKey: ["browser-imports"] });
    };
    window.addEventListener("campus-agent-import", listener);
    return () => window.removeEventListener("campus-agent-import", listener);
  }, [me.data, q]);
  useEffect(() => {
    if (!me.data || lock.current) return;
    const active = sessions.data?.filter((b) =>
      ["queued", "waiting_login", "waiting_timetable", "extracting"].includes(
        b.data.status,
      ),
    );
    if (!active?.length) return;
    lock.current = true;
    (async () => {
      for (let b of active) {
        try {
          const bind = await extension("restore", {
            sessionId: b.id,
            owner: me.data!.id,
          });
          if (!bind) continue;
          for (const event of bind.events) {
            const desired =
              event.kind === "opened" ? "waiting_login" : event.kind;
            const order = [
              "queued",
              "waiting_login",
              "waiting_timetable",
              "extracting",
              "preview_ready",
            ];
            if (
              event.kind !== "failed" &&
              order.indexOf(b.data.status) >= order.indexOf(desired)
            )
              continue;
            b = await api<Resource>(`/browser-imports/${b.id}/events`, {
              method: "POST",
              body: JSON.stringify({ ...event, revision: b.revision }),
              headers: { "Idempotency-Key": event.event_id },
            });
          }
          if (bind.capture && b.data.status === "extracting") {
            await api(`/browser-imports/${b.id}/capture`, {
              method: "POST",
              body: JSON.stringify({
                ...bind.capture,
                revision: b.revision,
                school_origin: new URL(b.data.entry_url).origin,
                adapter_version: b.data.adapter_version,
              }),
            });
            await extension("stop", { sessionId: b.id, owner: me.data!.id });
            q.invalidateQueries();
          }
        } catch (e) {
          setError(String(e));
        }
      }
    })().finally(() => {
      lock.current = false;
    });
  }, [sessions.data, sessions.dataUpdatedAt, me.data, q]);
  const latest = sessions.data?.at(-1);
  const draft = drafts.data?.find((d) => d.id === latest?.data.draft_id);
  function statusCard() {
    return (
      latest && (
        <div className="card">
          <p role="status">
            {labels[latest.data.status] ?? latest.data.status}
          </p>
          {latest.data.error && <p role="alert">{latest.data.error}</p>}
          {[
            "queued",
            "waiting_login",
            "waiting_timetable",
            "extracting",
            "preview_ready",
          ].includes(latest.data.status) && (
            <Button
              variant="outline"
              onClick={async () => {
                try {
                  await api(`/browser-imports/${latest.id}/cancel`, {
                    method: "POST",
                    body: JSON.stringify({ revision: latest.revision }),
                  });
                  pending.current = null;
                  await q.invalidateQueries();
                  await extension("stop", {
                    sessionId: latest.id,
                    owner: me.data!.id,
                  });
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              取消导入
            </Button>
          )}
        </div>
      )
    );
  }
  return (
    <>
      {showOverview && <p className="hint">
        点击导入可查看分步引导。学校登录后，请找到个人课表、选择学期并点击查询；提取后需本人确认保存。
      </p>}
      {!open && error && <p role="alert">{error}</p>}
      {!open && (showOverview || ["queued", "waiting_login", "waiting_timetable", "extracting", "preview_ready"].includes(latest?.data.status)) && statusCard()}
      {latest && !open && (showOverview || ["queued", "waiting_login", "waiting_timetable", "extracting", "preview_ready"].includes(latest.data.status)) && (
        <Button variant="outline" onClick={showGuide}>
          查看导入引导
        </Button>
      )}
      <ImportGuide
        open={open}
        onOpenChange={setOpen}
        phase={phase}
        onDetect={detect}
        onContinue={start}
        busy={busy}
        error={error}
      >
        {statusCard()}
        {draft && latest?.data.status === "preview_ready" && (
          <DraftReview key={draft.id} draft={draft} />
        )}
        {latest?.data.status === "completed" && (
          <Button onClick={() => setOpen(false)}>完成，查看课表</Button>
        )}
      </ImportGuide>
    </>
  );
}
