import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { DraftActions } from "./Assignments";
import { CampusPresetSelector, type CampusPresetId } from "./CampusPresetSelector";
import type { Resource } from "./types";

const fields = {name: "课程名称", teacher: "教师", campus: "校区", location: "教室", weekday: "星期", weeks_text: "周次", periods: "节次"};
type Field = keyof typeof fields;
type Evidence = {field: Field; text: string; page: number; bbox: number[] | null; bbox_note?: string | null};
type Candidate = {
  candidate_id: string; name: string | null; teacher: string | null; campus: string | null;
  location: string | null; weekday: number | null; weeks_text: string | null; periods: number[];
  reviewed: boolean; excluded: boolean; uncertain_fields: Field[]; evidence: Evidence[];
};
type Payload = {semester_label: string; semester_confirmed: boolean; campus_preset?: CampusPresetId | null; candidates: Candidate[]; warnings: string[]};

export function TimetableRecognitionInput() {
  const q = useQueryClient();
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const uploadKey = useRef(crypto.randomUUID()), jobKey = useRef(crypto.randomUUID());
  const jobs = useQuery({queryKey: ["timetable-jobs"], queryFn: () => api<Resource[]>("/timetable-jobs"),
    refetchInterval: d => d.state.data?.some(j => ["queued", "running"].includes(j.data.status)) ? 1500 : false});
  const states = jobs.data?.map(j => `${j.id}:${j.data.status}`).join(",");
  useEffect(() => { q.invalidateQueries({queryKey: ["drafts"]}); }, [states, q]);
  const running = jobs.data?.some(j => ["queued", "running"].includes(j.data.status));
  return <section className="card timetable-input">
    <h2>图片 / PDF 识别华工课表</h2>
    <p>拍照、截图：PNG/JPEG/WebP，≤10 MiB、≤20 百万像素。PDF：≤20 MiB、1–10 页，不支持加密文件。</p>
    <p>原件保存在本地；每页图片及 PDF 文字层交给已配置的视觉模型。结果只生成草稿，请逐门校对；未确定的上课时间不会保存。</p>
    <form onSubmit={async e => {
      e.preventDefault(); if (busy || running) return;
      setBusy(true); setError("");
      try {
        const data = new FormData(e.currentTarget);
        const file = data.get("timetable-file") as File;
        const body = new FormData(); body.set("file", file);
        const asset = await api<Resource>("/timetable-assets", {method: "POST", body, headers: {"Idempotency-Key": uploadKey.current}});
        await api("/timetable-jobs", {method: "POST", body: JSON.stringify({asset_id: asset.id, consent: true}), headers: {"Idempotency-Key": jobKey.current}});
        await q.invalidateQueries({queryKey: ["timetable-jobs"]});
      } catch (e) { setError(String(e)); } finally { setBusy(false); }
    }}>
      <label>课表图片或 PDF<input type="file" name="timetable-file" required accept="image/png,image/jpeg,image/webp,application/pdf"
        disabled={busy || running} onChange={() => {uploadKey.current = crypto.randomUUID(); jobKey.current = crypto.randomUUID(); setError("");}} /></label>
      <label className="check"><input type="checkbox" required disabled={busy || running} />我同意将这份课表的所有页面图片及文字发送给设置中的模型供应商</label>
      <Button disabled={busy || running}>{busy ? "正在上传并创建识别任务…" : running ? "正在识别课表…" : "识别课表，生成校对草稿"}</Button>
    </form>
    {jobs.data?.slice(-3).reverse().map(j => <div key={j.id} role="status" className="recognition-job">
      {j.data.status === "done" ? "已识别，请校对下方课表草稿" : j.data.status === "failed" ? j.data.error : `正在识别：${j.data.completed_pages} / ${j.data.total_pages} 页`}
      {j.data.status === "failed" && <Button variant="outline" disabled={busy || running} onClick={async () => {
        setBusy(true); setError("");
        try {await api("/timetable-jobs", {method: "POST", body: JSON.stringify({asset_id: j.data.asset_id, consent: true})}); await q.invalidateQueries({queryKey: ["timetable-jobs"]});}
        catch(e) {setError(String(e));} finally {setBusy(false);}
      }}>授权重新识别此原件</Button>}
    </div>)}
    {error && <p role="alert">{error}</p>}{jobs.error && <p role="alert">{String(jobs.error)}</p>}
  </section>;
}

export function TimetableRecognitionReview({draft}: {draft: Resource}) {
  const textInput = draft.data.draft_kind === "timetable_text";
  const [currentDraft, setCurrentDraft] = useState<Resource>(draft);
  const [payload, setPayload] = useState<Payload>(draft.data.payload);
  const [presetTouched, setPresetTouched] = useState(false);
  const [error, setError] = useState("");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [preview, setPreview] = useState<{fingerprint: string; data: {added: string[]; reused: string[]; existing_kept: number}} | null>(null);
  const [page, setPage] = useState(1), [box, setBox] = useState<number[] | null>(null);
  const assetId = draft.data.source.asset_id;
  const asset = useQuery({queryKey: ["timetable-asset", assetId], enabled: !textInput, queryFn: () => api<Resource>("/timetable-assets/" + assetId)});
  const courses = useQuery({queryKey: ["courses"], queryFn: () => api<Resource[]>("/courses")});
  const settings = useQuery({queryKey: ["settings"], queryFn: () => api<Resource>("/settings")});
  const defaultPreset =
    (draft.data.payload.campus_preset as CampusPresetId | null | undefined) ??
    (settings.data?.data.campus_preset as CampusPresetId | null | undefined) ??
    null;
  const effectivePayload: Payload = {
    ...payload,
    campus_preset: presetTouched
      ? (payload.campus_preset ?? null)
      : defaultPreset,
  };
  const patch = (index: number, values: Partial<Candidate>) => setPayload(p => ({...p, campus_preset: effectivePayload.campus_preset, candidates: p.candidates.map((c, i) => i === index ? {...c, ...values} : c)}));
  const change = (index: number, field: Field, value: unknown) => patch(index, {[field]: value, reviewed: false,
    uncertain_fields: effectivePayload.candidates[index].uncertain_fields.filter(f => f !== field)});
  const missing = (c: Candidate) => (["name", "weekday", "weeks_text", "periods"] as Field[]).filter(k => k === "periods" ? !c.periods.length : !String(c[k] ?? "").trim());
  const included = effectivePayload.candidates.filter(c => !c.excluded);
  const canSave = effectivePayload.semester_confirmed && !!effectivePayload.semester_label.trim() && included.length > 0 && included.every(c => c.reviewed && !c.uncertain_fields.length && !missing(c).length);
  const fingerprint = JSON.stringify([effectivePayload, settings.data?.revision, courses.data?.map(c => [c.id,c.revision])]);
  const checked = preview?.fingerprint === fingerprint;
  const activeDraft = draft.revision > currentDraft.revision ? draft : currentDraft;
  return <section className="card timetable-recognition-review" aria-label={textInput ? "文字课表校对" : "课表识别校对"}>
    <p className="eyebrow">{textInput ? "文字课表草稿" : "华工课表识别草稿"} · 尚未保存</p><h2>{textInput ? "核对文字内容，逐门确认课程" : "对照原件，逐门确认课程"}</h2>
    <p>共 {effectivePayload.candidates.length} 个候选，保留 {included.length} 个。当前已保存 {courses.data?.length ?? "…"} 条课程；保存时仅新增，完全相同的课程复用，不删除已有课程。</p>
    <p>请核对设置中的开学周一、学期周数与节次时间。非连续节次会分段占用，中间未上课的节次保持空闲；连续节次间的休息单独记录并保留。</p>
    <label>{textInput ? "文字课表的学期名称" : "识别课表的学期名称"}<input value={effectivePayload.semester_label} onChange={e => setPayload({...effectivePayload, semester_label: e.target.value, semester_confirmed: false})} /></label>
    {settings.data && <p>当前设置学期：{settings.data.data.semester_name || "未填写"}；首周周一：{settings.data.data.week1_monday || "未填写，请前往设置补齐"}；共 {settings.data.data.week_count} 周。</p>}
    <label className="check"><input type="checkbox" checked={effectivePayload.semester_confirmed} onChange={e => setPayload({...effectivePayload, semester_confirmed: e.target.checked})} />{textInput ? "确认这些课程属于上述学期，且与当前设置一致" : "确认这些页面属于上述学期，且与当前设置一致"}</label>
    <CampusPresetSelector
      value={effectivePayload.campus_preset ?? null}
      onChange={(next) => {
        setPresetTouched(true);
        setPayload({ ...effectivePayload, campus_preset: next });
      }}
    />
    {effectivePayload.warnings.map((w, i) => <p role="alert" key={i}>{w}</p>)}
    <div className="timetable-review-layout">
      <aside className="timetable-source">
        {textInput ? <><h3>对话原文</h3>{draft.data.source.messages.map((m: {run_id: string; text: string}) => <pre className="pdf-source-text" key={m.run_id}>{m.text}</pre>)}
          <p>缺失信息可以继续告诉助手，也可在右侧补齐。教师、教室、校区可留空。</p></> : <>
        <label>原件页码<select value={page} onChange={e => {setPage(Number(e.target.value)); setBox(null);}}>
          {Array.from({length: draft.data.source.page_count}, (_, i) => <option key={i} value={i+1}>第 {i+1} 页 · {({image:"图片", text_pdf:"文字 PDF", scanned_pdf:"扫描 PDF"} as Record<string,string>)[asset.data?.data.pages[i]?.type] ?? "读取中"}</option>)}
        </select></label>
        <a href={`/api/assets/${assetId}`} target="_blank" rel="noreferrer">打开原始文件</a>
        <div className="timetable-source-image"><img src={`/api/assets/${assetId}/pages/${page}`} alt={`课表原件第 ${page} 页`} />
          {box && <span aria-label="证据区域" className="evidence-box" style={{left:`${box[0]*100}%`,top:`${box[1]*100}%`,width:`${(box[2]-box[0])*100}%`,height:`${(box[3]-box[1])*100}%`}} />}
        </div>
        <p>点选字段证据可切换页码；橙框是模型给出的参考区域，仍需对照原图。</p>
        {asset.error && <p role="alert">{String(asset.error)}</p>}
        <details><summary>本地提取的文字层</summary><pre className="pdf-source-text">{asset.data?.data.pages[page-1]?.text || "无文字层，通过页面图片识别"}</pre></details></>}
      </aside>
      <div>{payload.candidates.length === 0 && <p role="alert">未提取到课程，请核对原件，重试识别或手工添加。</p>}
        {payload.candidates.map((c, i) => <fieldset key={c.candidate_id} className="recognition-candidate">
          <legend>课程 {i+1}{c.excluded ? " · 不导入" : ""}</legend>
          <label className="check"><input type="checkbox" checked={c.excluded} onChange={e => patch(i, {excluded: e.target.checked})} />不导入这门课程</label>
          <div className="grid2">
            {(["name", "teacher", "campus", "location", "weeks_text"] as const).map(k => <label key={k}>{fields[k]}{k === "weeks_text" ? "（如 1-16周(单)）" : ""}<input disabled={c.excluded} value={c[k] ?? ""} onChange={e => change(i,k,e.target.value || null)} /></label>)}
            <label>星期<select disabled={c.excluded} value={c.weekday ?? ""} onChange={e => change(i,"weekday",e.target.value ? Number(e.target.value) : null)}>
              <option value="">待补充</option>{["一","二","三","四","五","六","日"].map((n,j) => <option key={n} value={j+1}>星期{n}</option>)}
            </select></label>
            <label>节次（逗号分隔，如 1,2）<PeriodInput disabled={c.excluded} initial={c.periods} onChange={v => change(i,"periods",v)} /></label>
          </div>
          <p>待核对：{[...new Set([...c.uncertain_fields, ...missing(c)])].map(k => fields[k]).join("、") || (textInput ? "请核对原文后确认" : "请对照原件确认")}</p>
          <div className="timetable-evidence">{c.evidence.map((v,j) => <button type="button" className="evidence-link" key={j} onClick={() => {setPage(v.page); setBox(v.bbox);}}>
            第 {v.page} 页 · {fields[v.field]}：{v.text}{!v.bbox && `（${v.bbox_note || "未定位区域"}）`}
          </button>)}</div>
          <label className="check"><input type="checkbox" disabled={c.excluded || missing(c).length > 0} checked={c.reviewed} onChange={e => patch(i,{reviewed:e.target.checked, uncertain_fields: e.target.checked ? [] : c.uncertain_fields})} />已校对本课程全部填写值；空缺教师、教室或校区按未知保留</label>
        </fieldset>)}
      </div>
    </div>
    {error && <p role="alert">{error}</p>}
    <Button variant="outline" disabled={!canSave || previewBusy} onClick={async () => {
      setPreviewBusy(true); setError("");
      try {const data = await api<{added: string[]; reused: string[]; existing_kept: number}>(`/drafts/${draft.id}/timetable-preview`, {method:"POST", body:JSON.stringify({revision:activeDraft.revision,payload:effectivePayload})}); setPreview({fingerprint,data});}
      catch(e){setError(String(e));} finally {setPreviewBusy(false);}
    }}>{previewBusy ? "正在检查…" : "检查导入差异"}</Button>
    {checked && preview && <div role="status" className="recognition-diff"><p>将新增 {preview.data.added.length} 条：{preview.data.added.join("、") || "无"}</p><p>复用相同课程 {preview.data.reused.length} 条：{preview.data.reused.join("、") || "无"}；保留已有 {preview.data.existing_kept} 条，删除 0 条。</p></div>}
    <DraftActions draft={activeDraft} payload={effectivePayload} onError={setError} onSaved={setCurrentDraft} canSave={canSave && checked} blockedMessage={canSave ? "请先检查导入差异，再确认保存。" : "请补齐学期与每门课程的名称、星期、周次、节次，逐门确认；不需要的课程可勾选不导入。"} />
  </section>;
}

function PeriodInput({initial, disabled, onChange}: {initial: number[]; disabled: boolean; onChange: (v: number[]) => void}) {
  const [text, setText] = useState(initial.join(","));
  return <input disabled={disabled} value={text} onChange={e => {
    const value = e.target.value; setText(value);
    onChange(/^\s*\d+(?:\s*[,，]\s*\d+)*\s*$/.test(value) ? value.split(/[,，]/).map(Number) : []);
  }} />;
}
