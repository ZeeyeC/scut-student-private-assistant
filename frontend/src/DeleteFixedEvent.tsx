import {useState} from "react";
import {useMutation, useQueryClient} from "@tanstack/react-query";
import {api} from "./api";
import {Button} from "./components/ui/button";

export function DeleteFixedEvent({id, revision, title, onDeleted}: {
  id: string; revision: number; title: string; onDeleted?: () => void;
}) {
  const query = useQueryClient();
  const [key, setKey] = useState("");
  const deletion = useMutation({
    mutationFn: () => api(`/fixed-events/${id}`, {
      method: "DELETE",
      headers: {"Idempotency-Key": key},
      body: JSON.stringify({revision}),
    }),
    onSuccess: async () => {
      await query.invalidateQueries();
      onDeleted?.();
    },
  });
  return <div>
    {key ? <>
      <p>删除「{title}」？</p>
      <Button variant="outline" disabled={deletion.isPending} onClick={()=>deletion.mutate()}>确认删除事项</Button>
      <Button variant="outline" disabled={deletion.isPending} onClick={()=>{deletion.reset();setKey("");}}>取消</Button>
    </> : <Button variant="outline" onClick={()=>setKey(crypto.randomUUID())}>删除事项</Button>}
    {deletion.error && <p role="alert">{String(deletion.error)}</p>}
  </div>;
}
