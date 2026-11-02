import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { Button } from "./components/ui/button";
import "./research-settings.css";

export type IntegrationsView = {
  semantic: { enabled: boolean; available: boolean; status: string; model: string; error?: string | null };
  search: { endpoint: string; configured: boolean };
};

export function ResearchSettings() {
  const qc = useQueryClient(), keys = useRef(new Map<string, string>());
  const [endpoint, setEndpoint] = useState(""), [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");

  const integrations = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api<IntegrationsView>("/integrations"),
    refetchInterval: (q) => (q.state.data?.semantic.status === "preparing" ? 1500 : false),
  });

  useEffect(() => {
    if (integrations.data && !dirty) setEndpoint(integrations.data.search.endpoint ?? "");
  }, [integrations.data, dirty]);

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
      await qc.invalidateQueries({ queryKey: ["integrations"] });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const sem = integrations.data?.semantic, search = integrations.data?.search;
  const isPreparing = sem?.status === "preparing";

  return (
    <section className="card research-settings" aria-label="检索与语义扩展" style={{ maxWidth: "100%" }}>
      <h2>检索与语义模型</h2>
      <p className="muted">语义检索为可选扩展：未准备、不可用或关闭时，记忆和资料检索会自动回退为本地关键词匹配，不会自动后台下载模型。</p>
      {(integrations.error || error || sem?.error) && <p role="alert">{error || sem?.error || String(integrations.error)}</p>}
      {notice && <p role="status">{notice}</p>}
      {integrations.isPending && <p className="muted">正在读取检索配置…</p>}
      {sem && (
        <div className="grid2" style={{ maxWidth: "100%", alignItems: "start" }}>
          <div>
            <h3>本地语义向量模型</h3>
            <p className="muted">模型：{sem.model || "未指定"} · 状态：{sem.status} · {sem.available ? "已就绪" : "未就绪（当前回退为关键词检索）"}</p>
            <p className="muted">首次准备需下载并加载本地向量模型，可能耗时并占用网络与磁盘空间；仅在手动确认后开始准备。</p>
            {isPreparing && <p role="status">正在下载并准备语义模型，请稍候…</p>}
            <div className="research-settings-actions">
              <label className="research-semantic-toggle">
                <input
                  type="checkbox"
                  checked={sem.enabled}
                  disabled={busy || isPreparing}
                  onChange={(e) => {
                    const next = e.target.checked;
                    void act(`sem-toggle:${next}`, (key) =>
                      api("/integrations/semantic", { method: "PUT", headers: { "Idempotency-Key": key }, body: JSON.stringify({ enabled: next }) }),
                    );
                  }}
                />
                <span>启用语义检索</span>
              </label>
              <Button
                type="button"
                variant="outline"
                disabled={busy || isPreparing}
                onClick={() => {
                  if (!window.confirm(`确认下载并准备语义模型（${sem.model}）？下载过程可能需要较长时间，失败或未完成时仍回退为关键词检索。`)) return;
                  void act("sem-prepare", (key) =>
                    api("/integrations/semantic/prepare", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({}) }),
                  );
                }}
              >{isPreparing ? "准备中…" : "准备语义模型"}</Button>
            </div>
          </div>
          {search && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const next = endpoint.trim();
                void act(
                  `search-ep:${next}`,
                  async (key) => {
                    await api("/integrations/search", { method: "PUT", headers: { "Idempotency-Key": key }, body: JSON.stringify({ endpoint: next }) });
                    setDirty(false);
                  },
                  "外部检索地址已更新",
                );
              }}
            >
              <h3>外部联网检索接口</h3>
              <p className="muted">当前状态：{search.configured ? "已配置外部检索服务" : "未配置（仅使用已入库资料与直接网页抓取）"}</p>
              <label>
                检索服务端点（URL）
                <input value={endpoint} placeholder="https://..." disabled={busy} onChange={(e) => { setEndpoint(e.target.value); setDirty(true); }} />
              </label>
              <div className="memory-actions"><Button variant="outline" disabled={busy}>保存检索地址</Button><Button type="button" variant="outline" disabled={busy||!endpoint.trim()} onClick={()=>void act('search-test:'+endpoint,async(key)=>{await api('/integrations/search/test',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({endpoint:endpoint.trim()})});},'搜索连接正常')}>测试连接</Button></div>
            </form>
          )}
        </div>
      )}
    </section>
  );
}
export default ResearchSettings;
