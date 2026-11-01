import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { Button } from "./components/ui/button";

export type ZoteroStatus = {
  enabled: boolean;
  mode: "local" | "remote";
  endpoint: string;
  connected: boolean | null;
  available: boolean;
  tools: string[];
  error?: string | null;
  revision: number;
  token_configured: boolean;
};

type ZoteroTestResult = { connected: boolean; tools: string[]; error?: string | null };

const CAPABILITY_LABELS = [
  { key: "search", label: "文献检索" },
  { key: "metadata", label: "论文信息" },
  { key: "fulltext", label: "全文" },
  { key: "notes", label: "笔记与批注" },
  { key: "collections", label: "文献分类" },
] as const;

export function ZoteroSettings() {
  const qc = useQueryClient(), keys = useRef(new Map<string, string>());
  const [enabled, setEnabled] = useState(false), [mode, setMode] = useState<"local" | "remote">("local");
  const [endpoint, setEndpoint] = useState(""), [token, setToken] = useState(""), [clearToken, setClearToken] = useState(false);
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [testState, setTestState] = useState<ZoteroTestResult | null>(null);

  const statusQuery = useQuery({
    queryKey: ["zotero-status"],
    queryFn: () => api<ZoteroStatus>("/zotero/status"),
  });

  useEffect(() => {
    if (statusQuery.data && !dirty) {
      setEnabled(Boolean(statusQuery.data.enabled));
      setMode(statusQuery.data.mode === "remote" ? "remote" : "local");
      setEndpoint(statusQuery.data.endpoint ?? "");
    }
  }, [statusQuery.data, dirty]);

  const getKey = (sig: string) => {
    const k = keys.current.get(sig) ?? crypto.randomUUID();
    keys.current.set(sig, k);
    return k;
  };

  async function act(sig: string, fn: (key: string) => Promise<void>, doneMsg = "") {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn(getKey(sig));
      keys.current.delete(sig);
      if (doneMsg) setNotice(doneMsg);
      await qc.invalidateQueries({ queryKey: ["zotero-status"] });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const st = statusQuery.data;
  const conn = testState ? testState.connected : (st?.connected ?? null);
  const connLabel = conn === true ? "已连接" : conn === false ? "连接失败" : "未测试";
  const activeError = error || testState?.error || st?.error || (statusQuery.error ? String(statusQuery.error) : "");

  return (
    <section className="card" aria-label="Zotero 文献库连接" style={{ maxWidth: "100%" }}>
      <h2>Zotero 文献库</h2>
      <p className="muted">连接后可在助手中检索论文、阅读全文与批注。使用时，相关内容会交给已配置的模型；文献库保持只读。</p>
      {activeError && <p role="alert">{activeError}</p>}
      {notice && <p role="status">{notice}</p>}
      {statusQuery.isPending && <p className="muted">正在读取 Zotero 配置…</p>}
      <div className="grid2" style={{ maxWidth: "100%", alignItems: "start" }}>
        <div>
          <h3>连接状态与只读能力</h3>
          <p className="muted">启用状态：{st?.enabled ? "已启用" : "未启用"} · 模式：{(st?.mode ?? mode) === "remote" ? "远程 MCP" : "本地桌面版"} · 连接状态：{connLabel}</p>
          <p className="muted">支持 5 项只读能力（不提供写入、修改或删除操作）：</p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            {CAPABILITY_LABELS.map((item) => (
              <span key={item.key} className="muted" style={{ border: "1px solid currentColor", borderRadius: 4, padding: "2px 6px", fontSize: 12 }}>{item.label}</span>
            ))}
          </div>
          <div className="memory-actions" style={{ marginTop: 10 }}>
            <Button type="button" variant="outline" disabled={busy || statusQuery.isPending} onClick={() => void act("zotero-test", async (key) => {
              setTestState(null);
              try {
                const res = await api<ZoteroTestResult>("/zotero/test", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({}) });
                setTestState(res);
                setNotice(res.connected ? "Zotero 连接测试成功" : "Zotero 连接测试未通过");
              } catch (e) {setTestState({connected:false,tools:[]});throw e;}
            })}>测试连接</Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => {
              setDirty(false); setToken(""); setClearToken(false); setError(""); setNotice(""); setTestState(null);
              void qc.invalidateQueries({ queryKey: ["zotero-status"] });
            }}>刷新配置</Button>
          </div>
        </div>
        <form onSubmit={(e) => {
          e.preventDefault();
          const rev = st?.revision ?? 0, ep = mode === "remote" ? endpoint.trim() : "", trimmedToken = mode === "remote" ? token.trim() : "";
          const body: Record<string, unknown> = { revision: rev, enabled, mode, endpoint: ep };
          if (trimmedToken) body.token = trimmedToken;
          if (clearToken) body.clear_token = true;
          const sig = `zotero-save:${rev}:${enabled}:${mode}:${ep}:${clearToken}:${trimmedToken}`;
          void act(sig, async (key) => {
            await api("/zotero/settings", { method: "PUT", headers: { "Idempotency-Key": key }, body: JSON.stringify(body) });
            keys.current.clear(); setToken(""); setClearToken(false); setDirty(false); setTestState(null);
          }, "Zotero 设置已保存（连接状态需点击“测试连接”验证）");
        }}>
          <h3>连接参数设置</h3>
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
            <input type="checkbox" checked={enabled} disabled={busy} onChange={(e) => { setEnabled(e.target.checked); setDirty(true); }} />
            启用 Zotero 文献库只读接入
          </label>
          <label>
            连接模式
            <select value={mode} disabled={busy} onChange={(e) => { setMode(e.target.value as "local" | "remote"); setDirty(true); }}>
              <option value="local">本机 Zotero</option>
              <option value="remote">已有 MCP 服务</option>
            </select>
          </label>
          {mode === "local" ? (
            <p className="muted">请打开 Zotero，在“设置 → 高级”中允许本机其他应用与 Zotero 通信。课间会使用内置的只读连接，无需终端配置。</p>
          ) : (
            <>
              <p className="muted">远程 URL 仅支持 HTTPS 或本地回环 HTTP（localhost / 127.0.0.1），且不得包含账号密码、查询参数（?）或锚点（#）。</p>
              <label>远程 MCP 端点（URL）<input value={endpoint} placeholder="https://example.com/mcp" disabled={busy} onChange={(e) => { setEndpoint(e.target.value); setDirty(true); }} /></label>
              <label>访问令牌（可选，{st?.token_configured ? "已配置：留空保留原令牌" : "未配置"}）<input type="password" value={token} autoComplete="off" placeholder="留空则保持已保存令牌不变" disabled={busy} onChange={(e) => { setToken(e.target.value); setDirty(true); }} /></label>
              <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={clearToken} disabled={busy} onChange={(e) => { setClearToken(e.target.checked); setDirty(true); }} />
                清除已保存的访问令牌
              </label>
            </>
          )}
          <div className="memory-actions"><Button variant="outline" disabled={busy || statusQuery.isPending}>保存 Zotero 设置</Button></div>
        </form>
      </div>
    </section>
  );
}
export default ZoteroSettings;
