import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { LocalSettings } from "./LocalMode";
import type { Resource } from "./types";
import {
  CAMPUS_PRESETS,
  CampusPresetSelector,
  type CampusPresetId,
} from "./CampusPresetSelector";
import { AfterClassPreferences } from "./AfterClass";
import {PersonalProfile} from "./PersonalProfile";
import {StudyTypes} from "./StudyTypes";
import {DetailPanel} from "./layout/DetailPanel";
import {SettingsAbout} from "./SettingsAbout";
import {ImportBrowserSettings} from "./SchoolImportPanel";
import {ProactiveSettings} from "./ProactiveSuggestions";
import {PageHeader} from './layout/PageHeader';
import {CalendarDays,Clock,Bell,MessageSquare,Folder,ChevronRight} from 'lucide-react';
type Form = {
  timezone: string;
  semester_name: string;
  week1_monday: string;
  week_count: number;
  daily_limit_minutes: number;
  max_block_minutes: number;
  min_block_minutes: number;
  buffer_minutes: number;
  campus_preset: CampusPresetId | null;
  periodRows: { number: number; start: string; end: string }[];
  study_windows: { start: string; end: string }[];
};
const settingGroups = [
  {id:'semester',title:'课程与学期',summary:'学期、节次、课程规则'},
  {id:'preferences',title:'学习偏好',summary:'学习时段、专注与休息'},
  {id:'reminders',title:'提醒与桌宠',summary:'提醒、显示与动作'},
  {id:'models',title:'模型连接',summary:'服务与连接配置'},
  {id:'data',title:'资料与备份',summary:'本机资料、导入与导出'},
] as const;
type SettingsGroup = typeof settingGroups[number]['id'];
export function Settings({local=false}:{local?:boolean}) {
  const [group,setGroup]=useState<SettingsGroup>('semester'),[open,setOpen]=useState(false);
  const settings=useQuery({queryKey:['settings'],queryFn:()=>api<Resource>('/settings')});
  const icons={semester:CalendarDays,preferences:Clock,reminders:Bell,models:MessageSquare,data:Folder};
  return <><PageHeader title="设置"/><div className="settings-list">{settingGroups.map(item=>{const Icon=icons[item.id];return <button type="button" key={item.id} aria-label={item.title} onClick={()=>{setGroup(item.id);setOpen(true);}}><Icon size={16}/><span><strong>{item.title}</strong><small>{item.summary}</small></span><span className="settings-summary-value">{item.id==='semester'?settings.data?.data.semester_name:item.id==='data'&&local?'本机保存':''}</span><ChevronRight size={16}/></button>;})}</div>
    <DetailPanel open={open} title={settingGroups.find(item=>item.id===group)!.title} onClose={()=>setOpen(false)}><SettingsContent key={group} local={local} group={group}/></DetailPanel>
  </>;
}
function SettingsContent({local,group}:{local:boolean;group:SettingsGroup}) {
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
  const { register, control, reset, handleSubmit, formState, watch, setValue } =
    useForm<Form>();
  const periods = useFieldArray({ control, name: "periodRows" }),
    windows = useFieldArray({ control, name: "study_windows" });
  const campusPreset = watch("campus_preset");
  useEffect(() => {
    if (s.data) {
      const d = s.data.data;
      reset({
        ...d,
        campus_preset: (d.campus_preset ?? null) as CampusPresetId | null,
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
      {group==='semester'&&<ImportBrowserSettings/>}
      {group==='preferences'&&<PersonalProfile/>}
      {group==='reminders'&&<><AfterClassPreferences/><ProactiveSettings/></>}
      {(group==='semester'||group==='preferences')&&<form
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
                  campus_preset: data.campus_preset ?? null,
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
        {group==='semester'&&<><section className="card">
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
          <CampusPresetSelector
            mode="settings"
            value={campusPreset ?? null}
            onChange={(next) => {
              setValue("campus_preset", next, { shouldDirty: true });
              if (next) {
                const found = CAMPUS_PRESETS.find((p) => p.id === next);
                if (found) {
                  periods.replace(
                    Object.entries(found.periods).map(([number, p]) => ({
                      number: Number(number),
                      start: p.start,
                      end: p.end,
                    })),
                  );
                }
              }
            }}
          />
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
                    onChange: () =>
                      setValue("campus_preset", null, { shouldDirty: true }),
                  })}
                />
              </label>
              <label>
                开始
                <input
                  type="time"
                  required
                  {...register(`periodRows.${i}.start`, {
                    onChange: () =>
                      setValue("campus_preset", null, { shouldDirty: true }),
                  })}
                />
              </label>
              <label>
                结束
                <input
                  type="time"
                  required
                  {...register(`periodRows.${i}.end`, {
                    onChange: () =>
                      setValue("campus_preset", null, { shouldDirty: true }),
                  })}
                />
              </label>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setValue("campus_preset", null, { shouldDirty: true });
                  periods.remove(i);
                }}
              >
                移除
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setValue("campus_preset", null, { shouldDirty: true });
              periods.append({
                number: periods.fields.length + 1,
                start: "",
                end: "",
              });
            }}
          >
            添加节次
          </Button>
        </section>
        </>}
        {group==='preferences'&&<section className="card">
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
        }
        <Button disabled={formState.isSubmitting}>保存设置</Button>
        {status && <p role="status">{status}</p>}
        {error && <p role="alert">{error}</p>}
      </form>}
      {group==='models'&&<>
      {local && <LocalSettings />}
      <section className="card">
        <h2>连接状态</h2>
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
      </section></>}
      {group==='data'&&<SettingsAbout/>}
      {group==='data'&&      <section className="card">
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
      </section>}
      {group==='preferences'&&<details><summary>管理课程与任务分类</summary><StudyTypes/></details>}
    </>
  );
}
export function FixedEvents() {
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
