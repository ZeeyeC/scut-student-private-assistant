import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { Button } from "./components/ui/button";
import type { Resource } from "./types";
import { DraftReview } from "./DraftReview";
import { TaskDetail } from "./TaskDetail";
import { navigate } from "./drafts";
import { DeleteButton } from "./DeleteButton";
import {DraftActions} from "./ReviewedDraftActions";
export {DraftActions} from "./ReviewedDraftActions";
export function AssignmentsPage({embedded = false}: {embedded?: boolean}) {
  const q = useQueryClient(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [jobId, setJobId] = useState("");
  const tasks = useQuery({
    queryKey: ["tasks"],
    queryFn: () => api<Resource[]>("/tasks"),
  });
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    enabled: !!jobId,
    queryFn: () => api<Resource>("/jobs/" + jobId),
    refetchInterval: (data) =>
      ["done", "failed"].includes(data.state.data?.data.status) ? false : 1500,
  });
  useEffect(() => {
    if (job.data?.data.status === "done")
      q.invalidateQueries({ queryKey: ["drafts"] });
  }, [job.data?.data.status, q]);
  return (
    <>
      <p className="eyebrow">ONE THING AT A TIME</p>
      {embedded ? <h2>添加与管理待办</h2> : <h1>待办与作业</h1>}
      <p>先校对内容，再把大作业变成可以开始的小步骤。</p>
      <section className="card">
        <h2>已保存的待办与作业</h2>
        <p>普通待办也保存在这里；未确认的内容在下方草稿区。</p>
        <Button variant="outline" onClick={()=>navigate("助手")}>用自然语言添加待办</Button>
        {tasks.data?.length === 0 && <p>还没有已保存的待办。</p>}
        {tasks.data?.map(t=><TaskCard key={t.id} task={t}/>)}
      </section>
      <div className="grid2">
        <form
          className="card"
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setBusy(true);
            setError("");
            try {
              const file = f.get("file") as File;
              const body = new FormData();
              body.set("file", file);
              const a = await api<Resource>("/assets", {
                method: "POST",
                body,
              });
              const reference = f.get("reference");
              const j = await api<Resource>("/assignment-jobs", {
                method: "POST",
                body: JSON.stringify({
                  asset_id: a.id,
                  consent: true,
                  reference_time: reference
                    ? new Date(String(reference)).toISOString()
                    : null,
                }),
              });
              setJobId(j.id);
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <h2>从截图识别</h2>
          <p>PNG/JPEG/WebP · 单张 ≤10 MiB、≤20 百万像素</p>
          <label>
            作业截图
            <input
              name="file"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              required
            />
          </label>
          <label>
            消息日期（相对日期的校对依据，可留空）
            <input name="reference" type="datetime-local" />
          </label>
          <label className="check">
            <input type="checkbox" required />
            我同意将图片及课程候选发送给服务端配置的模型供应商
          </label>
          <Button disabled={busy}>
            {busy ? "正在上传…" : "识别并生成草稿"}
          </Button>
          {job.data && (
            <p role="status">
              {
                {
                  queued: "排队中",
                  running: "正在识别",
                  done: "已识别，请校对下方草稿",
                  failed: job.data.data.error,
                }[job.data.data.status as string]
              }
            </p>
          )}
        </form>
        <form
          className="card"
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setBusy(true);
            try {
              await api("/drafts/assignment", {
                method: "POST",
                body: JSON.stringify({
                  items: [
                    {
                      title: f.get("title"),
                      requirements: String(f.get("requirements"))
                        .split("\n")
                        .filter(Boolean),
                      due_at: f.get("due")
                        ? new Date(String(f.get("due"))).toISOString()
                        : null,
                    },
                  ],
                  warnings: [],
                }),
              });
              q.invalidateQueries({ queryKey: ["drafts"] });
              e.currentTarget?.reset();
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <h2>手工添加</h2>
          <label>
            作业标题
            <input name="title" required />
          </label>
          <label>
            要求（一行一项）
            <textarea name="requirements" rows={3} />
          </label>
          <label>
            明确的截止时间（不清楚请留空）
            <input name="due" type="datetime-local" />
          </label>
          <Button disabled={busy}>生成校对草稿</Button>
        </form>
      </div>
      {error && <p role="alert">{error}</p>}
      {drafts.data
        ?.filter((d) => d.data.draft_kind === "assignment")
        .map((d) => (
          <DraftReview key={d.id} draft={d} />
        ))}
      {tasks.isPending && <p>正在读取作业…</p>}
      {tasks.error && <p role="alert">{String(tasks.error)}</p>}
      {tasks.data?.length === 0 && (
        <div className="card">
          <h2>还没有作业</h2>
          <p>上传一张截图，或手工添加第一项。</p>
        </div>
      )}

    </>
  );
}
export function TaskCard({ task }: { task: Resource }) {
  const [open, setOpen] = useState(false);
  const q = useQueryClient();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const steps = useQuery({queryKey:["steps",task.id], queryFn:()=>api<Resource[]>(`/tasks/${task.id}/steps`)});
  const drafts = useQuery({queryKey:["drafts"], queryFn:()=>api<Resource[]>("/drafts")});
  const stepDrafts = drafts.data?.filter(d=>d.data.draft_kind === "decomposition" && d.data.payload.task_id === task.id) ?? [];
  return (
    <article className="card">
      <h2>{task.data.title}</h2>
      <p>
        {task.data.due_at
          ? "截止 " + new Date(task.data.due_at).toLocaleString("zh-CN")
          : "截止时间待确认"}{" "}
        · {task.data.status === "completed" ? "已完成" : task.data.status === "archived" ? "已归档" : "进行中"}
      </p>
      {task.data.due_text && <p>原始时间描述：{task.data.due_text}</p>}
      {task.data.status === "open" && steps.data?.length === 0 && <form onSubmit={async e=>{
        e.preventDefault(); const minutes = Number(new FormData(e.currentTarget).get("minutes"));
        setBusy(true); setError("");
        try {await api(`/tasks/${task.id}/step-drafts`, {method:"POST",body:JSON.stringify({
          task_revision:task.revision,steps:[{key:"work",title:task.data.title,description:task.data.requirements.join("；") || task.data.title,
          estimated_minutes:minutes,dependency_keys:[],acceptance_criteria:["完成本项待办要求"]}]
        })}); q.invalidateQueries({queryKey:["drafts"]});}
        catch(e){setError(String(e));} finally{setBusy(false);}
      }}>
        <p>此待办尚无可排程步骤。填写实际预计耗时，或展开下方步骤请 AI 拆解。</p>
        <label>预计耗时（分钟）<input name="minutes" type="number" min={5} max={240} required /></label>
        <Button disabled={busy || stepDrafts.length > 0}>{busy ? "正在生成…" : "生成排程步骤草稿"}</Button>
      </form>}
      {error && <p role="alert">{error}</p>}
      {!open && stepDrafts.map(d=><DraftReview key={d.id} draft={d}/>)}
      <ul>
        {task.data.requirements?.map((r: string, i: number) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
      <Button variant="outline" onClick={() => setOpen(!open)}>
        {open ? "收起步骤" : "查看 / 拆解步骤"}
      </Button>
      <DeleteButton resource={task} disabled={busy} />
      {open && <TaskDetail task={task} />}
    </article>
  );
}
export function AssignmentReview({ draft }: { draft: Resource }) {
  const courses = useQuery({
    queryKey: ["courses"],
    queryFn: () => api<Resource[]>("/courses"),
  });
  const [payload, setPayload] = useState(draft.data.suggested_payload ?? draft.data.payload),
    [error, setError] = useState("");
  const change = (i: number, key: string, value: unknown) =>
    setPayload({
      ...payload,
      items: payload.items.map((x: Record<string, unknown>, j: number) =>
        i === j ? { ...x, [key]: value } : x,
      ),
    });
  return (
    <section className={payload.asset_id ? "card assignment-review with-image" : "card assignment-review"}>
      <p className="eyebrow">作业草稿 · 尚未保存</p>
      <h2>{payload.asset_id ? "核对原图和识别结果" : "核对任务草稿"}</h2>
      <div className="assignment-review-body">
        {payload.asset_id && (
          <img
            className="source-image"
            src={"/api/assets/" + payload.asset_id}
            alt="待校对的作业原图"
          />
        )}
        <div>
          {payload.items.map((item: Record<string, any>, i: number) => (
            <fieldset key={i} className="assignment-fields">
              <legend>作业 {i + 1}</legend>
              <label className="field-wide">
                标题
                <input
                  value={item.title}
                  onChange={(e) => change(i, "title", e.target.value)}
                />
              </label>
              <label>
                关联课程
                <select
                  value={item.course_id ?? ""}
                  onChange={(e) =>
                    change(i, "course_id", e.target.value || null)
                  }
                >
                  <option value="">待确认 / 不关联课程</option>
                  {courses.data?.map((c) => (
                    <option value={c.id} key={c.id}>
                      {c.data.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                提交方式
                <input
                  value={item.submission_method ?? ""}
                  onChange={(e) =>
                    change(i, "submission_method", e.target.value || null)
                  }
                />
              </label>
              <label className="field-wide">
                要求
                <textarea
                  value={item.requirements.join("\n")}
                  onChange={(e) =>
                    change(i, "requirements", e.target.value.split("\n"))
                  }
                />
              </label>
              <div className="field-wide deadline-context">
              <p>原文截止描述：{item.due_text || "未识别到明确日期"}</p>
              <p>待确认：{item.uncertain_fields.map((f: string) => f === "due_at" ? "截止日期与时间" : f).join("、") || "无"}</p>
              {item.deadline_basis && item.due_at && <p className="deadline-inference">
                {item.deadline_basis.kind === "calendar_boundary"
                  ? item.deadline_basis.reference_date
                    ? `按消息日期 ${item.deadline_basis.reference_date} 补全年份/相对日期：`
                    : "按原文日期边界解析："
                  : `按首周周一 ${item.deadline_basis.week1_monday} 推算：`}
                {item.deadline_basis.expression} = {new Date(item.due_at).toLocaleString("zh-CN", {timeZone:item.deadline_basis.timezone, hour12:false})}
                （{item.deadline_basis.timezone}，日期边界）。已自动填写，直接校对后保存；也可以告诉助手修改日期。
              </p>}
              </div>
              <label className="field-wide">
                确认后的截止时间
                <input
                  type="datetime-local"
                  value={
                    item.due_at
                      ? new Date(
                          new Date(item.due_at).getTime() -
                            new Date(item.due_at).getTimezoneOffset() * 60000,
                        )
                          .toISOString()
                          .slice(0, 16)
                      : ""
                  }
                  onChange={(e) => {
                    const value = e.target.value
                      ? new Date(e.target.value).toISOString()
                      : null;
                    setPayload({
                      ...payload,
                      items: payload.items.map(
                        (x: Record<string, any>, j: number) =>
                          j === i
                            ? {
                                ...x,
                                due_at: value,
                                deadline_basis: null,
                                uncertain_fields: value
                                  ? x.uncertain_fields.filter(
                                      (f: string) => f !== "due_at",
                                    )
                                  : [
                                      ...new Set([
                                        ...x.uncertain_fields,
                                        "due_at",
                                      ]),
                                    ],
                              }
                            : x,
                      ),
                    });
                  }}
                />
              </label>
              {item.evidence?.map((v: Record<string, string>, j: number) => (
                <small className="field-wide" key={j}>
                  {v.field}：{v.text}
                  <br />
                </small>
              ))}
            </fieldset>
          ))}
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      <DraftActions draft={draft} payload={payload} onError={setError} />
    </section>
  );
}
