// Shared save-control integration for the planning-side conflict service.
// Execution, task state and profile storage remain owned by developer B.
import {useState} from "react";
import {useQueryClient} from "@tanstack/react-query";
import {api} from "./api";
import type {Resource} from "./types";
import {Button} from "./components/ui/button";
import {DeleteButton} from "./DeleteButton";
import {ConflictReview, type ConflictReport} from "./ConflictReview";

export function DraftActions({
  draft,
  payload,
  onError,
  canSave = true,
  blockedMessage = "没有可保存的安排，补齐信息后重新生成。",
}: {
  draft: Resource;
  payload: unknown;
  onError: (e: string) => void;
  canSave?: boolean;
  blockedMessage?: string;
}) {
  const q = useQueryClient(),
    [ask, setAsk] = useState(false),
    [busy, setBusy] = useState(false),
    [saved, setSaved] = useState<Resource>(draft),
    [key] = useState(crypto.randomUUID());
  const needsCheck = ["timetable", "timetable_recognition", "timetable_text", "calendar_event", "course_change"].includes(draft.data.draft_kind);
  const fingerprint = JSON.stringify(payload);
  const [review,setReview] = useState<{fingerprint:string;report:ConflictReport}|null>(null);
  const [acknowledged,setAcknowledged] = useState(false);
  const ready = ask && (!needsCheck || review?.fingerprint===fingerprint);
  return <div className="draft-actions">
    {!canSave ? <p role="status">{blockedMessage}</p> : !ready ? (
    <Button type="button" disabled={busy} onClick={async () => {
      setBusy(true);onError("");setAcknowledged(false);
      try {
        if(needsCheck){const report=await api<ConflictReport>(`/drafts/${draft.id}/conflict-preview`,{method:"POST",body:JSON.stringify({revision:saved.revision,payload})});setReview({fingerprint,report});}
        setAsk(true);
      } catch(e){onError(String(e));} finally{setBusy(false);}
    }}>{busy ? "正在检查冲突…" : "校对完成，准备保存"}</Button>
  ) : (
    <div className="confirm">
      {needsCheck && review && <><ConflictReview report={review.report} />{(review.report.conflict_count>0 || review.report.complete===false) && <label className="check"><input type="checkbox" checked={acknowledged} onChange={e=>setAcknowledged(e.target.checked)} />我已核对上述提示，仍按已确认的课程或事项保存</label>}</>}
      <p>{draft.data.draft_kind === "course_change" ? "确认仅调整本次课程？其他周课程和已有学习安排保留。" : draft.data.draft_kind === "scheduling_constraint" ? "确认保存禁排？后续新计划将遵守它；已有安排需重新规划并确认后才调整。" : ["timetable", "timetable_recognition", "timetable_text"].includes(draft.data.draft_kind) ? "确认保存课程？课程将进入固定课表，智能安排会避让这些时间。" : "确认保存以上内容？保存后显示在待办与日程中。"}</p>
      <Button
        type="button"
        disabled={busy || (needsCheck && (!!review?.report.conflict_count || review?.report.complete===false) && !acknowledged)}
        onClick={async () => {
          setBusy(true);
          try {
            const edited =
              JSON.stringify(saved.data.payload) === JSON.stringify(payload)
                ? saved
                : await api<Resource>(`/drafts/${draft.id}`, {
                    method: "PUT",
                    body: JSON.stringify({ revision: saved.revision, payload }),
                  });
            setSaved(edited);
            await api(`/drafts/${draft.id}/confirm`, {
              method: "POST",
              body: JSON.stringify({ revision: edited.revision, ...(needsCheck ? {conflict_token:review?.report.conflict_token} : {}) }),
              headers: { "Idempotency-Key": key },
            });
            q.invalidateQueries();
            if (draft.data.draft_kind === "course_change") window.dispatchEvent(new Event("campus-course-change-saved"));
            if (draft.data.draft_kind === "calendar_event") {
              window.dispatchEvent(new CustomEvent("campus-calendar-saved", {detail: edited.data.payload.starts_at}));
            }
          } catch (e) {
            onError(String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        确认保存
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          setAsk(false);
        }}
      >
        继续校对
      </Button>
    </div>
  )}
    <DeleteButton resource={saved.revision > draft.revision ? saved : draft} disabled={busy} />
  </div>;
}
