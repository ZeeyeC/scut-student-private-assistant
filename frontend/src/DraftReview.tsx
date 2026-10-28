import { useState } from "react";
import type { Resource, Timetable, Course } from "./types";
import { AssignmentReview, DraftActions } from "./Assignments";
import { DecompositionReview } from "./TaskDetail";
import { EventReview } from "./EventReview";
import { PlanReview } from "./Today";
import { CourseChangeReview } from "./CourseChanges";
import { ConstraintReview } from "./SchedulingConstraints";
import { TimetableRecognitionReview } from "./TimetableRecognition";

export function DraftReview({ draft }: { draft: Resource }) {
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
  const [payload, setPayload] = useState(draft.data.payload as Timetable);
  const [error, setError] = useState("");
  const update = (i: number, k: keyof Course, v: unknown) =>
    setPayload({
      ...payload,
      courses: payload.courses.map((c, j) => (j === i ? { ...c, [k]: v } : c)),
    });
  return (
    <section className="card">
      <p className="eyebrow">待你校对 · 尚未保存</p>
      <h2>课表预览</h2>
      <p>
        {payload.semester_label} · {payload.courses.length} 门课程
      </p>
      <p>
        新增{" "}
        {String(
          (draft.data.changes as { added: unknown[] })?.added?.length ?? 0,
        )}{" "}
        · 更新 {draft.data.changes?.changed?.length ?? 0} · 未出现{" "}
        {draft.data.changes?.possibly_removed?.length ?? 0}（保留）
      </p>
      {payload.warnings?.map((w, i) => (
        <p role="alert" key={i}>
          {w}
        </p>
      ))}
      {payload.courses.map((c, i) => (
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
      <DraftActions draft={draft} payload={payload} onError={setError} />
    </section>
  );
}
