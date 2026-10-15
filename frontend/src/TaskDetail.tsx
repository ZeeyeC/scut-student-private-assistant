import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Resource } from "./types";
import { Button } from "./components/ui/button";
import { DraftActions } from "./Assignments";
export function TaskDetail({ task }: { task: Resource }) {
  const q = useQueryClient(),
    [error, setError] = useState(""),
    [consent, setConsent] = useState(false),
    [manual, setManual] = useState(false),
    [busy, setBusy] = useState(false);
  const steps = useQuery({
    queryKey: ["steps", task.id],
    queryFn: () => api<Resource[]>(`/tasks/${task.id}/steps`),
  });
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  return (
    <div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          try {
            await api("/tasks/" + task.id, {
              method: "PATCH",
              body: JSON.stringify({
                revision: task.revision,
                due_at: f.get("due")
                  ? new Date(String(f.get("due"))).toISOString()
                  : task.data.due_at,
                remedy_due_at: f.get("remedy")
                  ? new Date(String(f.get("remedy"))).toISOString()
                  : task.data.remedy_due_at,
                priority: Number(f.get("priority")),
              }),
            });
            q.invalidateQueries();
          } catch (e) {
            setError(String(e));
          }
        }}
      >
        <div className="grid2">
          <label>
            更新明确截止时间
            <input name="due" type="datetime-local" />
          </label>
          <label>
            逾期后补救截止时间
            <input name="remedy" type="datetime-local" />
          </label>
          <label>
            优先级
            <select name="priority" defaultValue={task.data.priority}>
              <option value="1">低</option>
              <option value="2">普通</option>
              <option value="3">高</option>
            </select>
          </label>
        </div>
        <Button variant="outline">确认更新作业</Button>
      </form>
      <label className="check">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        允许将本项作业内容发送给模型进行拆解
      </label>
      <Button
        disabled={!consent || busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/tasks/${task.id}/decompose`, {
              method: "POST",
              body: JSON.stringify({ consent: true }),
            });
            q.invalidateQueries({ queryKey: ["drafts"] });
          } catch (e) {
            setError(String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        提出任务拆解
      </Button>
      <Button variant="outline" onClick={() => setManual(!manual)}>
        手工编辑步骤
      </Button>
      <Button
        variant="outline"
        onClick={async () => {
          try {
            await api("/tasks/" + task.id, {
              method: "PATCH",
              body: JSON.stringify({
                revision: task.revision,
                status: task.data.status === "completed" ? "open" : "completed",
              }),
            });
            q.invalidateQueries();
          } catch (e) {
            setError(String(e));
          }
        }}
      >
        {task.data.status === "completed" ? "重新打开作业" : "确认作业完成"}
      </Button>
      {manual && (
        <StepsEditor
          initial={[blankStep(0)]}
          onSubmit={async (steps) => {
            await api(`/tasks/${task.id}/step-drafts`, {
              method: "POST",
              body: JSON.stringify({ task_revision: task.revision, steps }),
            });
            q.invalidateQueries({ queryKey: ["drafts"] });
            setManual(false);
          }}
        />
      )}
      {error && <p role="alert">{error}</p>}
      {drafts.data
        ?.filter(
          (d) =>
            d.data.draft_kind === "decomposition" &&
            d.data.payload.task_id === task.id,
        )
        .map((d) => (
          <DecompositionReview draft={d} key={d.id} />
        ))}
      {steps.isPending && <p>正在读取步骤…</p>}
      {steps.data?.map((s) => (
        <form
          key={s.id + ":" + s.revision}
          className="step"
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            try {
              await api("/steps/" + s.id, {
                method: "PATCH",
                body: JSON.stringify({
                  revision: s.revision,
                  spent_minutes: Number(f.get("spent")),
                  estimated_minutes: Number(f.get("estimate")),
                }),
              });
              q.invalidateQueries();
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          <h3>
            {s.data.title} ·{" "}
            {s.data.status === "completed"
              ? "已完成"
              : "剩余 " +
                Math.max(0, s.data.estimated_minutes - s.data.spent_minutes) +
                " 分钟"}
          </h3>
          <p>{s.data.description}</p>
          <ul>
            {s.data.acceptance_criteria.map((x: string, i: number) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
          <div className="grid2">
            <label>
              预计分钟（估计，可改）
              <input
                name="estimate"
                type="number"
                min={5}
                max={240}
                defaultValue={s.data.estimated_minutes}
              />
            </label>
            <label>
              已投入分钟
              <input
                name="spent"
                type="number"
                min={0}
                defaultValue={s.data.spent_minutes}
              />
            </label>
          </div>
          <Button variant="outline">记录投入和估计</Button>
          <Button
            type="button"
            variant="outline"
            onClick={async () => {
              try {
                await api("/steps/" + s.id, {
                  method: "PATCH",
                  body: JSON.stringify({
                    revision: s.revision,
                    status:
                      s.data.status === "completed" ? "open" : "completed",
                  }),
                });
                q.invalidateQueries();
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            {s.data.status === "completed" ? "重新打开步骤" : "确认步骤完成"}
          </Button>
        </form>
      ))}
    </div>
  );
}
const blankStep = (i: number) => ({
  key: "step-" + (i + 1),
  title: "",
  description: "",
  estimated_minutes: 30,
  dependency_keys: [] as string[],
  acceptance_criteria: [""],
});
type Step = ReturnType<typeof blankStep>;
function StepsEditor({
  initial,
  onSubmit,
}: {
  initial: Step[];
  onSubmit: (steps: Step[]) => Promise<void>;
}) {
  const [steps, setSteps] = useState(initial),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const change = (i: number, k: keyof Step, v: unknown) =>
    setSteps(steps.map((s, j) => (i === j ? { ...s, [k]: v } : s)));
  return (
    <form
      className="card"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onSubmit(steps);
        } catch (e) {
          setError(String(e));
        } finally {
          setBusy(false);
        }
      }}
    >
      <p>每项 5–240 分钟，耗时是估计；依赖填写其他步骤的标识，用逗号分隔。</p>
      {steps.map((s, i) => (
        <fieldset key={s.key}>
          <legend>{s.key}</legend>
          <label>
            步骤标题
            <input
              required
              value={s.title}
              onChange={(e) => change(i, "title", e.target.value)}
            />
          </label>
          <label>
            具体行动
            <textarea
              required
              value={s.description}
              onChange={(e) => change(i, "description", e.target.value)}
            />
          </label>
          <label>
            估计分钟
            <input
              type="number"
              min={5}
              max={240}
              value={s.estimated_minutes}
              onChange={(e) =>
                change(i, "estimated_minutes", Number(e.target.value))
              }
            />
          </label>
          <label>
            前置依赖
            <input
              value={s.dependency_keys.join(",")}
              onChange={(e) =>
                change(
                  i,
                  "dependency_keys",
                  e.target.value.split(",").filter(Boolean),
                )
              }
            />
          </label>
          <label>
            完成标准（一行一项）
            <textarea
              required
              value={s.acceptance_criteria.join("\n")}
              onChange={(e) =>
                change(i, "acceptance_criteria", e.target.value.split("\n"))
              }
            />
          </label>
        </fieldset>
      ))}
      <Button
        type="button"
        variant="outline"
        disabled={steps.length >= 12}
        onClick={() => setSteps([...steps, blankStep(steps.length)])}
      >
        添加步骤
      </Button>
      <Button disabled={busy}>生成可确认草稿</Button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
export function DecompositionReview({ draft }: { draft: Resource }) {
  const [payload, setPayload] = useState(draft.data.payload),
    [error, setError] = useState("");
  return (
    <div className="card">
      <h2>拆解草稿 · 耗时为估计</h2>
      <StepsEditor
        initial={payload.steps}
        onSubmit={async (steps) => {
          setPayload({ ...payload, steps });
        }}
      />
      <p>先点击“生成可确认草稿”应用你的编辑，再确认保存。</p>
      <DraftActions draft={draft} payload={payload} onError={setError} />
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
