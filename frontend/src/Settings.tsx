import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { LocalSettings } from "./LocalMode";
import type { Resource } from "./types";
import { AfterClassPreferences } from "./AfterClass";
type Form = {
  timezone: string;
  semester_name: string;
  week1_monday: string;
  week_count: number;
  daily_limit_minutes: number;
  max_block_minutes: number;
  min_block_minutes: number;
  buffer_minutes: number;
  periodRows: { number: number; start: string; end: string }[];
  study_windows: { start: string; end: string }[];
};
export function Settings({ local = false }: { local?: boolean }) {
  const q = useQueryClient(),
    [status, setStatus] = useState(""),
    [error, setError] = useState(""),
    [deleteText, setDeleteText] = useState("");
  const s = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Resource>("/settings"),
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Record<string, boolean>>("/healthz"),
  });
  const { register, control, reset, handleSubmit, formState } = useForm<Form>();
  const periods = useFieldArray({ control, name: "periodRows" }),
    windows = useFieldArray({ control, name: "study_windows" });
  useEffect(() => {
    if (s.data) {
      const d = s.data.data;
      reset({
        ...d,
        week1_monday: d.week1_monday ?? "",
        periodRows: Object.entries(d.periods).map(([number, p]) => ({
          number: Number(number),
          ...(p as { start: string; end: string }),
        })),
      } as Form);
    }
  }, [s.data, reset]);
  if (s.isPending) return <p>正在读取设置…</p>;
  if (s.error) return <p role="alert">{String(s.error)}</p>;
  return (
    <>
      <h1>学习设置</h1>
      <p>
        这里的默认学习窗口是个人安排建议。学期锚点和节次请按学校实际信息校对。
      </p>
      <form
        onSubmit={handleSubmit(async (v) => {
          try {
            setError("");
            if (
              new Set(v.periodRows.map((x) => x.number)).size !==
              v.periodRows.length
            )
              throw new Error("节次标识重复");
            const { periodRows, ...data } = v;
            await api("/settings", {
              method: "PUT",
              body: JSON.stringify({
                revision: s.data!.revision,
                data: {
                  ...data,
                  week1_monday: data.week1_monday || null,
                  periods: Object.fromEntries(
                    periodRows.map((p) => [
                      p.number,
                      { start: p.start, end: p.end },
                    ]),
                  ),
                },
              }),
            });
            await q.invalidateQueries({ queryKey: ["settings"] });
            setStatus("设置已保存");
          } catch (e) {
            setError(String(e));
          }
        })}
      >
        <section className="card">
          <h2>学期与时区</h2>
          <div className="grid2">
            <label>
              学期名称
              <input {...register("semester_name")} />
            </label>
            <label>
              第一周周一
              <input type="date" {...register("week1_monday")} />
            </label>
            <label>
              学期周数
              <input
                type="number"
                min={1}
                max={30}
                {...register("week_count", { valueAsNumber: true })}
              />
            </label>
            <label>
              时区
              <input {...register("timezone", { required: true })} />
            </label>
          </div>
        </section>
        <section className="card">
          <h2>实际节次时间</h2>
          <p>没有节次映射时，课程无法参与排程。此处不会默认填入学校作息。</p>
          {periods.fields.map((p, i) => (
            <div className="period-row" key={p.id}>
              <label>
                节次
                <input
                  type="number"
                  min={1}
                  max={30}
                  {...register(`periodRows.${i}.number`, {
                    valueAsNumber: true,
                  })}
                />
              </label>
              <label>
                开始
                <input
                  type="time"
                  required
                  {...register(`periodRows.${i}.start`)}
                />
              </label>
              <label>
                结束
                <input
                  type="time"
                  required
                  {...register(`periodRows.${i}.end`)}
                />
              </label>
              <Button
                type="button"
                variant="outline"
                onClick={() => periods.remove(i)}
              >
                移除
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              periods.append({
                number: periods.fields.length + 1,
                start: "",
                end: "",
              })
            }
          >
            添加节次
          </Button>
        </section>
        <section className="card">
          <h2>学习窗口与上限</h2>
          {windows.fields.map((w, i) => (
            <div className="period-row" key={w.id}>
              <label>
                学习开始
                <input type="time" {...register(`study_windows.${i}.start`)} />
              </label>
              <label>
                学习结束
                <input type="time" {...register(`study_windows.${i}.end`)} />
              </label>
              <Button
                variant="outline"
                type="button"
                onClick={() => windows.remove(i)}
              >
                移除
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => windows.append({ start: "19:00", end: "21:00" })}
          >
            添加学习窗口
          </Button>
          <div className="grid2">
            {(
              [
                ["daily_limit_minutes", "每日学习上限（分钟）"],
                ["max_block_minutes", "单块最长分钟"],
                ["min_block_minutes", "最短有效空闲分钟"],
                ["buffer_minutes", "课程 / 固定事项缓冲分钟"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  {...register(key, { valueAsNumber: true })}
                />
              </label>
            ))}
          </div>
        </section>
        <Button disabled={formState.isSubmitting}>保存设置</Button>
        {status && <p role="status">{status}</p>}
        {error && <p role="alert">{error}</p>}
      </form>
      <AfterClassPreferences />
      {local && <LocalSettings />}
      <FixedEvents />
      <section className="card">
        <h2>模型与课表扩展</h2>
        <p>
          聊天模型：
          {health.data?.model_configured
            ? "已配置，真实调用需验收"
            : "未配置"}{" "}
          · 图片模型：
          {health.data?.vision_configured
            ? "已配置，图片能力需真实验收"
            : "未配置"}
        </p>
        <p>
          华工适配：
          {health.data?.scut_verified
            ? "有适配配置，需逐字段核对"
            : "external_input_required，尚未提供实测配置"}
        </p>
        <p>
          扩展安装：构建后在 Chrome / Edge 扩展页面打开开发者模式，加载
          extension/.output/chrome-mv3 文件夹。开发助手地址必须为
          http://127.0.0.1:5173。共享站点按说明使用 PUBLIC_ORIGIN 重新构建。
        </p>
      </section>
      <section className="card">
        <h2>我的数据</h2>
        <Button
          variant="outline"
          onClick={async () => {
            try {
              const data = await api("/data-export");
              const url = URL.createObjectURL(
                new Blob([JSON.stringify(data, null, 2)], {
                  type: "application/json",
                }),
              );
              const a = document.createElement("a");
              a.href = url;
              a.download = "campus-data.json";
              a.click();
              URL.revokeObjectURL(url);
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          导出个人数据
        </Button>
        <label>
          删除全部课程、任务、图片与会话，输入“删除我的所有数据”
          <input
            value={deleteText}
            onChange={(e) => setDeleteText(e.target.value)}
          />
        </label>
        <Button
          variant="outline"
          disabled={deleteText !== "删除我的所有数据"}
          onClick={async () => {
            try {
              await api("/data-delete", {
                method: "POST",
                body: JSON.stringify({ confirmation: deleteText }),
              });
              setDeleteText("");
              setStatus("个人数据已删除");
              q.invalidateQueries();
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          确认删除我的数据
        </Button>
      </section>
    </>
  );
}
function FixedEvents() {
  const q = useQueryClient(),
    [error, setError] = useState("");
  const events = useQuery({
    queryKey: ["fixed-events"],
    queryFn: () => api<Resource[]>("/fixed-events"),
  });
  return (
    <section className="card">
      <h2>固定事项</h2>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          try {
            await api("/fixed-events", {
              method: "POST",
              body: JSON.stringify({
                title: f.get("title"),
                starts_at: new Date(String(f.get("start"))).toISOString(),
                ends_at: new Date(String(f.get("end"))).toISOString(),
              }),
            });
            q.invalidateQueries();
          } catch (e) {
            setError(String(e));
          }
        }}
      >
        <label>
          事项名称
          <input name="title" required />
        </label>
        <div className="grid2">
          <label>
            开始时间
            <input name="start" type="datetime-local" required />
          </label>
          <label>
            结束时间
            <input name="end" type="datetime-local" required />
          </label>
        </div>
        <Button>确认添加固定事项</Button>
      </form>
      {events.data?.map((e) => (
        <p key={e.id}>
          {e.data.title} · {new Date(e.data.starts_at).toLocaleString("zh-CN")}{" "}
          <Button
            variant="outline"
            onClick={async () => {
              try {
                await api("/fixed-events/" + e.id, {
                  method: "DELETE",
                  body: JSON.stringify({ revision: e.revision }),
                });
                q.invalidateQueries();
              } catch (x) {
                setError(String(x));
              }
            }}
          >
            删除事项
          </Button>
        </p>
      ))}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
