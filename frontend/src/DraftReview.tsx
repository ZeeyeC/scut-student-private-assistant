import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Resource, Timetable, Course } from "./types";
import { CampusPresetSelector, type CampusPresetId } from "./CampusPresetSelector";
import { AssignmentReview, DraftActions } from "./Assignments";
import { DecompositionReview } from "./TaskDetail";
import { EventReview } from "./EventReview";
import { PlanReview } from "./Today";
import { CourseChangeReview } from "./CourseChanges";
import { ConstraintReview } from "./SchedulingConstraints";
import { TimetableRecognitionReview } from "./TimetableRecognition";

import { SemesterCalendarReview } from "./SemesterCalendar";

export function DraftReview({ draft }: { draft: Resource }) {
  if (draft.data.draft_kind === "semester_calendar")
    return <SemesterCalendarReview draft={draft} key={draft.id+":"+draft.revision} />;
  if (draft.data.draft_kind === "course_change")
    return <CourseChangeReview draft={draft} key={draft.id+":"+draft.revision} />;
  if (["timetable_recognition", "timetable_text"].includes(draft.data.draft_kind))
    return <TimetableRecognitionReview draft={draft} key={draft.id + ":" + draft.revision} />;
  if (draft.data.draft_kind === "scheduling_constraint")
    return <ConstraintReview draft={draft} key={draft.id + ":" + draft.revision} />;
  if (draft.data.draft_kind === "calendar_event")
    return <EventReview draft={draft} key={draft.id + ":" + draft.revision} />;
  if (draft.data.draft_kind === "assignment")
    return <AssignmentReview draft={draft} key={draft.id + ":" + draft.revision} />;
  if (draft.data.draft_kind === "decomposition")
    return <DecompositionReview draft={draft} />;
  if (draft.data.draft_kind === "plan") return <PlanReview draft={draft} />;
  return <TimetableReview draft={draft} />;
}
function TimetableReview({ draft }: { draft: Resource }) {
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Resource>("/settings"),
  });
  const [payload, setPayload] = useState(draft.data.payload as Timetable);
  const [presetTouched, setPresetTouched] = useState(false);
  const [error, setError] = useState("");
  const defaultPreset =
    (draft.data.payload.campus_preset as CampusPresetId | null | undefined) ??
    (settings.data?.data.campus_preset as CampusPresetId | null | undefined) ??
    null;
  const effectivePayload: Timetable = {
    ...payload,
    campus_preset: presetTouched
      ? (payload.campus_preset ?? null)
      : defaultPreset,
  };
  const update = (i: number, k: keyof Course, v: unknown) =>
    setPayload({
      ...effectivePayload,
      courses: effectivePayload.courses.map((c, j) => (j === i ? { ...c, [k]: v } : c)),
    });
  return (
    <section className="card">
      <p className="eyebrow">待你校对 · 尚未保存</p>
      <h2>课表预览</h2>
      <p>
        {effectivePayload.semester_label} · {effectivePayload.courses.length} 门课程
      </p>
      <p>
        新增{" "}
        {String(
          (draft.data.changes as { added: unknown[] })?.added?.length ?? 0,
        )}{" "}
        · 更新 {draft.data.changes?.changed?.length ?? 0} · 未出现{" "}
        {draft.data.changes?.possibly_removed?.length ?? 0}（{effectivePayload.save_mode==='replace'?'确认覆盖后移除':'保留'}）
      </p>
      <CampusPresetSelector
        value={effectivePayload.campus_preset ?? null}
        onChange={(next) => {
          setPresetTouched(true);
          setPayload({ ...effectivePayload, campus_preset: next });
        }}
      />
      <label className="check"><input type="checkbox" checked={effectivePayload.save_mode==='replace'} onChange={e=>setPayload({...effectivePayload,save_mode:e.target.checked?'replace':'merge'})}/>替换当前课表</label>
      {effectivePayload.save_mode==='replace'&&<p role="status">本次校对结果将替换全部已保存课程；未出现在本次结果中的旧课程会被移除。旧课程的调课入口停用，历史记录、待办和固定事项保留；确认保存前不改动课表。</p>}
      {effectivePayload.warnings?.map((w, i) => (
        <p role="alert" key={i}>
          {effectivePayload.save_mode==='replace'&&w.includes('不删除已有课程')?'本次采集尚无完整性证明；请确认所需课程全部在下方，再覆盖旧课表。':w}
        </p>
      ))}
      {effectivePayload.courses.map((c, i) => (
        <fieldset key={i} className="grid2">
          <legend>{c.name}</legend>
          <label>
            课程
            <input
              value={c.name}
              onChange={(e) => update(i, "name", e.target.value)}
            />
          </label>
          <label>
            地点
            <input
              value={c.location ?? ""}
              onChange={(e) => update(i, "location", e.target.value)}
            />
          </label>
          <label>
            星期
            <input
              type="number"
              min={1}
              max={7}
              value={c.weekday}
              onChange={(e) => update(i, "weekday", Number(e.target.value))}
            />
          </label>
          <label>
            周次
            <input
              value={c.weeks.join(",")}
              onChange={(e) =>
                update(i, "weeks", e.target.value.split(",").map(Number))
              }
            />
          </label>
          <label>
            节次
            <input
              value={c.periods.join(",")}
              onChange={(e) =>
                update(i, "periods", e.target.value.split(",").map(Number))
              }
            />
          </label>
        </fieldset>
      ))}
      {error && <p role="alert">{error}</p>}
      <DraftActions draft={draft} payload={effectivePayload} onError={setError} />
    </section>
  );
}
