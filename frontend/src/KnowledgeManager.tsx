import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { Button } from "./components/ui/button";
import type { Resource } from "./types";

type Chunk = { id: string; text: string; location?: string };
type SearchResult = { items: { source_id: string; title: string; location?: string; text: string }[]; mode: string };

export function KnowledgeManager({
  onSelect,
  selectedIds = [],
  disabled = false,
}: {
  onSelect?: (source: Resource) => void;
  selectedIds?: string[];
  disabled?: boolean;
}) {
  const qc = useQueryClient(), keys = useRef(new Map<string, string>());
  const [courseFilter, setCourseFilter] = useState(""), [uploadCourseId, setUploadCourseId] = useState("");
  const [file, setFile] = useState<File | null>(null), [url, setUrl] = useState(""), [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [searchResult, setSearchResult] = useState<SearchResult | null>(null);

  const sources = useQuery({ queryKey: ["knowledge-sources"], queryFn: () => api<Resource[]>("/knowledge/sources") });
  const courses = useQuery({ queryKey: ["courses"], queryFn: () => api<Resource[]>("/courses") });

  const getKey = (sig: string) => {
    const k = keys.current.get(sig) ?? crypto.randomUUID();
    keys.current.set(sig, k);
    return k;
  };
  const courseName = (id?: string | null) => courses.data?.find((c) => c.id === id)?.data.name ?? id ?? "未关联课程";
  const visibleSources = (sources.data ?? []).filter((s) => !courseFilter || s.data.course_id === courseFilter);

  async function run(sig: string, fn: (key: string) => Promise<void>) {
    if (busy || disabled) return;
    setBusy(true);
    setError("");
    try {
      await fn(getKey(sig));
      keys.current.delete(sig);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-label="课程资料库" style={{ maxWidth: "100%" }}>
      <h2>课程资料与检索</h2>
      <p className="muted">上传讲义文档或保存网页资料，按课程筛选并检索原文片段。</p>
      {(sources.error || courses.error || error) && <p role="alert">{error || String(sources.error ?? courses.error)}</p>}
      <div className="grid2" style={{ maxWidth: "100%", alignItems: "end" }}>
        <label>筛选课程<select value={courseFilter} onChange={(e) => setCourseFilter(e.target.value)} disabled={disabled}><option value="">全部课程</option>{courses.data?.map((c) => <option key={c.id} value={c.id}>{c.data.name}</option>)}</select></label>
        <label>入库关联课程（可选）<select value={uploadCourseId} onChange={(e) => setUploadCourseId(e.target.value)} disabled={disabled || busy}><option value="">不关联课程</option>{courses.data?.map((c) => <option key={c.id} value={c.id}>{c.data.name}</option>)}</select></label>
      </div>
      <div className="grid2" style={{ maxWidth: "100%", marginTop: 8 }}>
        <form onSubmit={(e) => {
          e.preventDefault();
          if (!file) return;
          const form = e.currentTarget, fd = new FormData();
          fd.append("file", file);
          if (uploadCourseId) fd.append("course_id", uploadCourseId);
          void run(`doc:${file.name}:${file.size}:${uploadCourseId}`, async (key) => {
            await api<{ id: string; revision: number }>("/knowledge/documents", { method: "POST", headers: { "Idempotency-Key": key }, body: fd });
            setFile(null);
            form.reset();
            await qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
          });
        }}>
          <label>上传文档<input type="file" disabled={disabled || busy} onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          <Button disabled={!file || busy || disabled}>上传资料</Button>
        </form>
        <form onSubmit={(e) => {
          e.preventDefault();
          const cleanUrl = url.trim();
          if (!cleanUrl) return;
          void run(`web:${cleanUrl}:${uploadCourseId}`, async (key) => {
            await api("/knowledge/web", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ url: cleanUrl, course_id: uploadCourseId || null }) });
            setUrl("");
            await qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
          });
        }}>
          <label>保存网页链接<input type="url" placeholder="https://..." value={url} disabled={disabled || busy} onChange={(e) => setUrl(e.target.value)} /></label>
          <Button variant="outline" disabled={!url.trim() || busy || disabled}>保存网页</Button>
        </form>
      </div>
      <form style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }} onSubmit={(e) => {
        e.preventDefault();
        const qText = query.trim();
        if (!qText) return;
        void run(`search:${qText}:${courseFilter}`, async (key) => {
          const res = await api<SearchResult>("/knowledge/search", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ query: qText, ...(courseFilter ? { course_id: courseFilter } : {}) }) });
          setSearchResult(res);
        });
      }}>
        <label style={{ flex: 1, minWidth: 180 }}>检索资料内容<input value={query} placeholder="输入关键词或问题…" disabled={disabled || busy} onChange={(e) => setQuery(e.target.value)} /></label>
        <Button variant="outline" disabled={!query.trim() || busy || disabled}>检索</Button>
      </form>
      {searchResult && (
        <div style={{ marginTop: 8 }}>
          <p className="muted">检索模式：{searchResult.mode} · 命中 {searchResult.items.length} 条</p>
          {searchResult.items.map((item, idx) => <p key={`${item.source_id}-${idx}`}><strong>{item.title}</strong> {item.location && <small className="muted">({item.location})</small>}：{item.text}</p>)}
        </div>
      )}
      <div style={{ marginTop: 8 }}>
        {sources.isPending && <p className="muted">正在加载资料…</p>}
        {!sources.isPending && !visibleSources.length && <p className="muted">暂无匹配的课程资料。</p>}
        {visibleSources.map((s) => {
          const chunks: Chunk[] = Array.isArray(s.data.chunks) ? s.data.chunks.slice(0, 20) : [];
          const selected = selectedIds.includes(s.id);
          return (
            <div key={s.id} style={{ borderTop: "1px solid var(--border, #ddd)", padding: "6px 0" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                <span><strong>{s.data.title || s.data.filename || s.id}</strong> <small className="muted">{s.data.format ?? "doc"} · {courseName(s.data.course_id)}{s.data.filename ? ` · ${s.data.filename}` : ""}{s.data.url ? ` · ${s.data.url}` : ""}</small></span>
                <span style={{ display: "flex", gap: 6 }}>
                  {onSelect && <Button type="button" variant={selected ? "default" : "outline"} disabled={disabled} onClick={() => onSelect(s)}>{selected ? "已选用" : "选用"}</Button>}
                  <Button type="button" variant="outline" disabled={busy || disabled} onClick={() => {
                    if (!window.confirm(`确认删除资料「${s.data.title || s.data.filename || s.id}」？`)) return;
                    void run(`del:${s.id}:${s.revision}`, async (key) => {
                      await api(`/knowledge/sources/${s.id}`, { method: "DELETE", headers: { "Idempotency-Key": key }, body: JSON.stringify({ revision: s.revision }) });
                      await qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
                    });
                  }}>删除</Button>
                </span>
              </div>
              <details>
                <summary className="muted">查看片段（前 {chunks.length} 条）</summary>
                {chunks.map((c) => <p key={c.id} style={{ margin: "4px 0" }}>{c.location && <small className="muted">[{c.location}] </small>}{c.text}</p>)}
              </details>
            </div>
          );
        })}
      </div>
    </section>
  );
}
export default KnowledgeManager;
