import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { Button } from "./components/ui/button";
import type { Resource } from "./types";

function draftTitle(draft: Resource) {
  const p = draft.data.payload;
  return (
    p.title ||
    p.items?.map((item: { title: string }) => item.title).join("、") ||
    (draft.data.draft_kind === "plan"
      ? `未来 ${p.horizon_days ?? 7} 天计划`
      : draft.data.draft_kind === "decomposition"
        ? "待办步骤拆解"
        : `${p.semester_label ?? ""}课表预览`)
  );
}

export function DeleteButton({ resource, disabled = false }: {
  resource: Resource;
  disabled?: boolean;
}) {
  const q = useQueryClient();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [target, setTarget] = useState({ revision: resource.revision, key: "" });
  const task = resource.kind === "task";
  const label = task ? "删除待办" : "删除草稿";
  function changeOpen(next: boolean) {
    if (busy) return;
    if (next) {
      setTarget({ revision: resource.revision, key: crypto.randomUUID() });
      setError("");
      setConflict(false);
    }
    setOpen(next);
  }
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api(`/${task ? "tasks" : "drafts"}/${resource.id}`, {
        method: "DELETE",
        body: JSON.stringify({ revision: target.revision }),
        headers: { "Idempotency-Key": target.key },
      });
      await q.invalidateQueries();
      setOpen(false);
    } catch (e) {
      setError(String(e));
      setConflict(e instanceof ApiError && (e.status === 409 || e.status === 404));
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    setBusy(true);
    try {
      await q.invalidateQueries();
      setOpen(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog.Root open={open} onOpenChange={changeOpen}>
      <Dialog.Trigger asChild>
        <Button type="button" variant="outline" className="delete-trigger" disabled={disabled}>
          {label}
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="import-dialog delete-dialog"
          onEscapeKeyDown={e => { if (busy) e.preventDefault(); }}
        >
          <Dialog.Title asChild><h2>{label}？</h2></Dialog.Title>
          <p className="delete-subject">
            {task ? resource.data.title : draftTitle(resource)}
          </p>
          <Dialog.Description>
            {task
              ? "这会同时删除此待办的全部步骤和学习安排，包含锁定和已完成的记录；相关拆解草稿和旧计划将失效，需要重新规划。此操作无法撤销。"
              : resource.data.source?.browser_session
                ? "这会丢弃本次课表预览并取消对应导入，已保存的课程保持不变。此操作无法撤销。"
                : "这会丢弃未保存的草稿，已保存的待办、课程和安排保持不变。此操作无法撤销。"}
          </Dialog.Description>
          {error && <p role="alert">{error}</p>}
          <div className="resource-actions">
            {conflict ? (
              <Button type="button" disabled={busy} onClick={refresh}>刷新内容</Button>
            ) : (
              <Button type="button" variant="destructive" disabled={busy} onClick={remove}>
                {busy ? "正在删除…" : "确认删除"}
              </Button>
            )}
            <Dialog.Close asChild>
              <Button type="button" variant="outline" disabled={busy}>取消</Button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
